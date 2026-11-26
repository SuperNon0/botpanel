"""Boutons d'action : Home Assistant, lien et webhook."""

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discord
import httpx
from pydantic import ValidationError

from app.bot import webhooks
from app.bot.views import build_notification_view
from app.config import settings
from app.db.database import init_db
from app.db.models import HaButton, Notification, NotificationButton, NotificationIn
from app.db.repositories import NotificationRepository


def _notif(**kw) -> Notification:
    base = dict(id=1, slug="recette", channel_id="1", title="t", message="m")
    base.update(kw)
    return Notification(**base)


class ButtonModelTests(unittest.TestCase):
    def test_ha_is_default_and_requires_service(self):
        self.assertEqual(HaButton(label="A", ha_service="light.toggle").action, "ha")
        with self.assertRaises(ValidationError):
            HaButton(label="A")

    def test_link_and_webhook_require_http_url(self):
        HaButton(label="Lire", action="link", url="https://exemple.fr/r/1")
        HaButton(label="Lire", action="link", url="{var:lien}")
        HaButton(label="Go", action="webhook", url="http://recipelog.lan/api/botpanel")
        for bad in (None, "", "ftp://x", "javascript:alert(1)"):
            with self.assertRaises(ValidationError):
                HaButton(label="Lire", action="link", url=bad)


class ButtonStorageAndViewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(settings, "database_path", Path(directory) / "test.db"))
        await init_db()

    async def test_buttons_round_trip(self):
        repo = NotificationRepository()
        created = await repo.create(NotificationIn(
            slug="recette", channel_id="1", title="t", message="m",
            buttons=[
                NotificationButton(label="Lumière", ha_service="light.toggle", ha_entity_id="light.salon"),
                NotificationButton(label="Lire", action="link", url="{var:lien}"),
                NotificationButton(label="Ajouter", action="webhook", url="https://site/api",
                                   ha_data_json='{"id": "{var:id}"}'),
            ],
        ))
        got = await repo.get_by_id(created.id)
        self.assertEqual([b.action for b in got.buttons], ["ha", "link", "webhook"])
        self.assertEqual(got.buttons[1].url, "{var:lien}")
        self.assertEqual(got.buttons[0].ha_service, "light.toggle")
        self.assertIsNone(got.buttons[1].ha_service)

    async def test_view_link_button_uses_vars_and_skips_invalid(self):
        notif = _notif(buttons=[
            NotificationButton(id=10, label="Lire", action="link", url="{var:lien}"),
            NotificationButton(id=11, label="Ajouter", action="webhook", url="https://site/api"),
            NotificationButton(id=12, label="Lumière", ha_service="light.toggle"),
        ])
        view = await build_notification_view(notif, {"lien": "https://recettes.lan/r/42"})
        link, hook, ha = view.children
        self.assertEqual(link.style, discord.ButtonStyle.link)
        self.assertEqual(link.url, "https://recettes.lan/r/42")
        self.assertEqual(hook.custom_id, "bp:btn:1:11")
        self.assertEqual(ha.custom_id, "bp:btn:1:12")

        # Sans variable : pas d'URL valide -> bouton lien omis (le message part quand meme).
        view = await build_notification_view(notif, None)
        self.assertEqual(len(view.children), 2)

    async def test_message_vars_round_trip(self):
        await webhooks.store_message_vars("999", {"id": "42"})
        self.assertEqual(await webhooks.load_message_vars("999"), {"id": "42"})
        self.assertEqual(await webhooks.load_message_vars("unknown"), {})

    async def test_webhook_call_is_signed_and_resolves_vars(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content
            seen["headers"] = request.headers
            return httpx.Response(200, json={"message": "Ajoutée à la liste"})

        real_client = httpx.AsyncClient

        def fake_client(**kw):
            return real_client(transport=httpx.MockTransport(handler), **kw)

        with patch.object(webhooks.httpx, "AsyncClient", fake_client):
            reply = await webhooks.call_webhook(
                "https://site/api/{var:id}",
                data_json='{"recette": "{var:id}", "n": 2}',
                variables={"id": "42"},
                context={"source": "notification", "button": "Ajouter"},
            )

        self.assertEqual(reply, "Ajoutée à la liste")
        self.assertEqual(seen["url"], "https://site/api/42")
        body = json.loads(seen["body"])
        self.assertEqual(body["data"], {"recette": "42", "n": 2})
        self.assertEqual(body["vars"], {"id": "42"})
        self.assertEqual(body["event"], "button_click")

        secret = await webhooks.get_webhook_secret()
        ts = seen["headers"]["X-BotPanel-Timestamp"]
        expected = "sha256=" + hmac.new(
            secret.encode(), ts.encode() + b"." + seen["body"], hashlib.sha256
        ).hexdigest()
        self.assertEqual(seen["headers"]["X-BotPanel-Signature"], expected)

    async def test_webhook_error_status_raises(self):
        real_client = httpx.AsyncClient

        def fake_client(**kw):
            return real_client(transport=httpx.MockTransport(lambda r: httpx.Response(500)), **kw)

        with patch.object(webhooks.httpx, "AsyncClient", fake_client):
            with self.assertRaises(webhooks.WebhookError):
                await webhooks.call_webhook("https://site/api", data_json=None,
                                            variables=None, context={})


if __name__ == "__main__":
    unittest.main()
