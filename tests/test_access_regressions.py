import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app import main
from app.api.server import app
from app.auth import COOKIE_NAME, hash_password
from app.bot.slash_sync import _build_generic_ha_command
from app.cloudflare_access import normalize_team
from app.config import settings
from app.db.database import init_db
from app.db.repositories import AuthRepository, SettingsRepository


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(settings, "database_path", Path(directory) / "test.db"))
        await init_db()
        self.client = await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ))
        self.settings = SettingsRepository()

    async def test_cloudflare_only_rejects_forged_headers_and_config_changes(self):
        await self.settings.set_many({"cf_allow_local": False, "cf_verify": False})
        headers = {"CF-Access-Authenticated-User-Email": "pretend@example.com"}
        for path, data in (
            ("/api/auth/cf-config", {"allow_local": True}),
            ("/api/auth/cf-test", {"team": "example.org/path"}),
            ("/api/auth/password", {"new_password": "newpassword"}),
        ):
            response = await self.client.post(path, json=data, headers=headers)
            self.assertEqual(response.status_code, 401)
        self.assertFalse(await self.settings.get("cf_allow_local"))
        self.assertEqual((await self.client.get("/api/dashboard", headers=headers)).status_code, 403)

    async def test_open_local_setup_can_configure_access_but_rejects_bad_team(self):
        response = await self.client.post("/api/auth/cf-config", json={"team": "example.org/path"})
        self.assertEqual(response.status_code, 422)
        response = await self.client.post("/api/auth/cf-config", json={"team": "https://my-team.cloudflareaccess.com/"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(await self.settings.get("cf_team"), "my-team")
        response = await self.client.post("/api/auth/cf-config", json={
            "team": "my-team", "aud": "test-aud", "allow_local": False,
        })
        self.assertEqual(response.status_code, 422)

    async def test_valid_cloudflare_badge_can_enable_and_manage_cloudflare_only(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = jwt.encode({"email": "admin@example.com", "iss": "https://my-team.cloudflareaccess.com",
                            "aud": "test-aud", "exp": int(time.time()) + 60}, key, algorithm="RS256")
        jwks = Mock()
        jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
        headers = {"CF-Access-Jwt-Assertion": token}
        payload = {"team": "my-team", "aud": "test-aud", "allow_local": False}
        with patch("app.cloudflare_access._get_jwk_client", return_value=jwks):
            response = await self.client.post("/api/auth/cf-config", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(await self.settings.get("cf_allow_local"))
            response = await self.client.get("/api/auth/cf-config", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["team"], "my-team")

    async def test_password_change_replaces_cookie_and_rejects_old_cookie(self):
        await AuthRepository().set_password(hash_password("oldpassword"))
        self.assertEqual((await self.client.post("/api/auth/login", json={"password": "oldpassword"})).status_code, 200)
        old_token = self.client.cookies[COOKIE_NAME]
        self.assertEqual((await self.client.post("/api/auth/password", json={
            "current_password": "oldpassword", "new_password": "newpassword",
        })).status_code, 200)
        self.assertNotEqual(self.client.cookies[COOKIE_NAME], old_token)
        self.assertTrue((await self.client.get("/api/auth/me")).json()["authenticated"])
        self.client.cookies.clear()
        response = await self.client.get("/api/auth/me", headers={"Cookie": f"{COOKIE_NAME}={old_token}"})
        self.assertFalse(response.json()["authenticated"])

    async def test_home_assistant_stays_accessible_in_cloudflare_only_mode(self):
        await self.settings.set_many({"cf_allow_local": False, "integration_api_key": "machine-key"})
        response = await self.client.get("/api/integration/ping", headers={"X-API-Key": "machine-key"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIsNotNone(await self.settings.get("integration_last_seen"))
        self.assertEqual((await self.client.get("/api/integration/ping")).status_code, 401)
        with patch("app.api.routes.ha_hook.send_notification", new=AsyncMock(return_value=SimpleNamespace(id=42))) as send:
            response = await self.client.post("/api/notify", json={"id": "ha_test", "vars": {"device": "test"}})
        self.assertEqual(response.json(), {"status": "sent", "message_id": "42"})
        send.assert_awaited_once_with("ha_test", {"device": "test"}, source="api")


class DiscordTests(unittest.IsolatedAsyncioTestCase):
    async def test_ha_command_requires_admin_and_allowed_service(self):
        member = Mock(spec=discord.Member)
        member.guild_permissions = discord.Permissions.none()
        interaction = SimpleNamespace(
            guild_id=42, user=member, response=AsyncMock(), followup=AsyncMock(),
        )
        command = _build_generic_ha_command()
        with patch.object(settings, "discord_guild_id", 42), \
             patch.object(settings, "discord_ha_allowed_services", "light.turn_on"), \
             patch("app.bot.slash_sync.ha_client.call_service", new=AsyncMock()) as call:
            await command.callback(interaction, "light.turn_on")
            member.guild_permissions = discord.Permissions(administrator=True)
            await command.callback(interaction, "lock.unlock")
            await command.callback(interaction, "light.turn_on", data="[]")
            call.assert_not_awaited()
            await command.callback(interaction, "light.turn_on", entity="light.kitchen")
            call.assert_awaited_once_with("light", "turn_on", {"entity_id": "light.kitchen"})

    async def test_discord_failure_keeps_http_task_alive(self):
        api_started = asyncio.Event()
        discord_failed = asyncio.Event()

        async def run_api():
            api_started.set()
            await asyncio.Future()

        async def fail_bot():
            discord_failed.set()
            raise RuntimeError("invalid Discord token")

        self.enterContext(patch.object(main, "settings", SimpleNamespace(is_configured=True)))
        self.enterContext(patch.object(main, "_configure_logging"))
        self.enterContext(patch.object(main, "init_db", new=AsyncMock()))
        self.enterContext(patch("app.auth.seed_from_env", new=AsyncMock()))
        self.enterContext(patch.object(main, "_run_api", new=run_api))
        self.enterContext(patch.object(main, "start_bot", new=fail_bot))
        self.enterContext(patch.object(main, "stop_bot", new=AsyncMock()))
        self.enterContext(patch.object(main.ha_client, "close", new=AsyncMock()))
        self.enterContext(patch.object(asyncio.get_running_loop(), "add_signal_handler", side_effect=NotImplementedError))
        with self.assertLogs(main.logger, level="ERROR"):
            task = asyncio.create_task(main._main())
            try:
                await asyncio.wait_for(api_started.wait(), timeout=2)
                await asyncio.wait_for(discord_failed.wait(), timeout=2)
                self.assertFalse(task.done())
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


class CloudflareNameTests(unittest.TestCase):
    def test_accepts_team_names_and_access_urls_only(self):
        self.assertEqual(normalize_team("https://my-team.cloudflareaccess.com/"), "my-team")
        for value in ("example.org/path", "x@local", "host:443", "cloudflareaccess.com/x", "../a", "-a"):
            with self.subTest(value=value):
                self.assertEqual(normalize_team(value), "")
