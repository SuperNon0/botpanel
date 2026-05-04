"""Wrapper autour de l'API REST de Home Assistant.

Utilise httpx en mode asynchrone avec un client unique partage par l'app.
Le token longue duree provient de la config.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class HomeAssistantError(Exception):
    """Erreur generique remontee par le client HA."""


class HomeAssistantClient:
    """Client HTTP pour l'API HA.

    Instancie un httpx.AsyncClient reutilisable. A fermer via `close()`
    (ou via le context manager) en fin de vie de l'application.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    # ---------- cycle de vie ----------
    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HomeAssistantClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ---------- helpers internes ----------
    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = path if path.startswith("/") else f"/{path}"
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("Erreur HTTP HA (%s %s) : %s", method, url, exc)
            raise HomeAssistantError(str(exc)) from exc

        if response.status_code >= 400:
            logger.error(
                "Reponse HA %s sur %s %s : %s",
                response.status_code, method, url, response.text,
            )
            raise HomeAssistantError(
                f"HA {response.status_code}: {response.text[:200]}"
            )

        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # ---------- endpoints haut niveau ----------
    async def ping(self) -> bool:
        """Verifie que l'API HA repond (GET /api/)."""
        try:
            await self._request("GET", "/api/")
            return True
        except HomeAssistantError:
            return False

    async def get_states(self) -> list[dict[str, Any]]:
        """Retourne l'etat de toutes les entites."""
        result = await self._request("GET", "/api/states")
        return result or []

    async def get_state(self, entity_id: str) -> Optional[dict[str, Any]]:
        """Retourne l'etat d'une entite ou None si absente."""
        try:
            return await self._request("GET", f"/api/states/{entity_id}")
        except HomeAssistantError:
            return None

    async def get_services(self) -> list[dict[str, Any]]:
        """Retourne la liste des domaines/services disponibles."""
        result = await self._request("GET", "/api/services")
        return result or []

    async def call_service(
        self,
        domain: str,
        service: str,
        data: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Declenche un service HA (ex: light.turn_on).

        Args:
            domain: domaine du service (ex: "light", "script").
            service: nom du service (ex: "turn_on", "toggle").
            data: payload additionnel (ex: {"entity_id": "light.salon"}).
        """
        payload = data or {}
        logger.info("HA call_service %s.%s payload=%s", domain, service, payload)
        return await self._request(
            "POST",
            f"/api/services/{domain}/{service}",
            json=payload,
        )

    async def render_template(self, template: str) -> str:
        """Demande a HA de rendre un template Jinja.

        POST /api/template -> renvoie la string rendue.
        Permet d'utiliser la syntaxe officielle HA dans les notifications :
            {{ states('sensor.x') }}
            {{ state_attr('sensor.x', 'attr') }}
            {% if ... %}...{% endif %}
        """
        try:
            result = await self._request(
                "POST",
                "/api/template",
                json={"template": template},
            )
        except HomeAssistantError as exc:
            logger.warning("Template HA non rendu (%s) : %s", template[:60], exc)
            raise
        # HA renvoie un texte brut (parfois dans un .text si non-JSON)
        return result if isinstance(result, str) else str(result)

    # ---------- helpers pour l'autocompletion du site ----------
    async def list_entity_ids(
        self, domain_filter: Optional[str] = None
    ) -> list[dict[str, str]]:
        """Retourne [{entity_id, friendly_name}] pour l'autocompletion.

        Args:
            domain_filter: si fourni, ne garde que les entites de ce domaine
                (ex: "light" pour ne renvoyer que les lumieres).
        """
        states = await self.get_states()
        result: list[dict[str, str]] = []
        for state in states:
            entity_id: str = state.get("entity_id", "")
            if not entity_id:
                continue
            if domain_filter and not entity_id.startswith(f"{domain_filter}."):
                continue
            friendly = state.get("attributes", {}).get("friendly_name") or entity_id
            result.append({"entity_id": entity_id, "friendly_name": friendly})
        result.sort(key=lambda e: e["friendly_name"].lower())
        return result

    async def list_services_flat(self) -> list[dict[str, str]]:
        """Applatit la liste des services en [{service, description}].

        Ex: ("light.turn_on", "Turn on a light").
        """
        services_domains = await self.get_services()
        flat: list[dict[str, str]] = []
        for domain_obj in services_domains:
            domain = domain_obj.get("domain", "")
            services = domain_obj.get("services", {})
            for service_name, service_data in services.items():
                full = f"{domain}.{service_name}"
                desc = (
                    service_data.get("description")
                    or service_data.get("name")
                    or full
                )
                flat.append({"service": full, "description": desc})
        flat.sort(key=lambda s: s["service"])
        return flat


# Singleton — instance partagee par le bot et l'API.
ha_client = HomeAssistantClient(
    base_url=settings.ha_base_url,
    token=settings.ha_token,
)
