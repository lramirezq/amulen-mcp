"""Cliente HTTP mínimo para la API v1 de AMULEN."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from . import __version__


class AmulenError(Exception):
    """Error devuelto por la API (o de conexión), con código legible."""

    def __init__(self, code: str, message: str, status: int | None = None, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details

    def __str__(self) -> str:
        text = f"{self.code}: {self.message}"
        if self.details:
            text += f" (detalles: {self.details})"
        return text


@dataclass
class Settings:
    base_url: str
    token: str
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.environ.get("AMULEN_BASE_URL", "").strip()
        token = os.environ.get("AMULEN_TOKEN", "").strip()
        if not base_url or not token:
            raise AmulenError(
                "config",
                "Faltan AMULEN_BASE_URL y/o AMULEN_TOKEN. Crea un token en AMULEN → Mi Perfil → Tokens de API.",
            )
        return cls(base_url=base_url.rstrip("/"), token=token, timeout=float(os.environ.get("AMULEN_TIMEOUT", "30")))


def seg(value: str) -> str:
    """Escapa un slug para usarlo como segmento de URL."""
    return quote(str(value), safe="")


class AmulenClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(
            base_url=f"{settings.base_url}/api/v1",
            headers={
                "Authorization": f"Bearer {settings.token}",
                "Accept": "application/json",
                "User-Agent": f"amulen-mcp/{__version__}",
            },
            timeout=settings.timeout,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = await self._http.request(method, path, params=params, json=json)
        except httpx.TimeoutException as e:
            raise AmulenError("timeout", f"AMULEN no respondió a tiempo ({e})") from e
        except httpx.HTTPError as e:
            raise AmulenError("connection", f"No se pudo conectar con AMULEN: {e}") from e

        if resp.status_code in (301, 302, 303, 307, 308):
            raise AmulenError(
                "redirect",
                f"AMULEN redirigió a {resp.headers.get('location')}: revisa AMULEN_BASE_URL (debe ser el subdominio de tu tenant)",
                resp.status_code,
            )
        try:
            body = resp.json()
        except ValueError:
            body = None

        if resp.is_success:
            return body
        err = (body or {}).get("error") if isinstance(body, dict) else None
        if err:
            raise AmulenError(err.get("code", "error"), err.get("message", ""), resp.status_code, err.get("details"))
        raise AmulenError("http_error", f"HTTP {resp.status_code}: {resp.text[:200]}", resp.status_code)

    async def get(self, path: str, **params: Any) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: dict) -> Any:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: dict) -> Any:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)
