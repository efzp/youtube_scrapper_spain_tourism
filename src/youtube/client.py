"""Cliente oficial de YouTube con reintentos transitorios limitados."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class YouTubeRequestError(RuntimeError):
    """Error seguro que no incluye URL ni credenciales de la peticion."""

    status_code: int | None
    reason: str

    def __str__(self) -> str:
        status = self.status_code if self.status_code is not None else "desconocido"
        return f"YouTube API respondio con estado {status}: {self.reason}"


def _safe_http_reason(error: HttpError) -> str:
    try:
        payload = json.loads(error.content.decode("utf-8"))
        api_error = payload.get("error", {})
        details = api_error.get("errors") or []
        if details and details[0].get("reason"):
            return str(details[0]["reason"])
        if api_error.get("message"):
            return str(api_error["message"])
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return "error de solicitud"


def execute_with_retry(
    operation: Callable[[], dict[str, Any]],
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Ejecuta una operacion y reintenta solo estados HTTP transitorios."""
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status not in TRANSIENT_HTTP_STATUSES or attempt == max_attempts:
                raise YouTubeRequestError(status, _safe_http_reason(exc)) from exc
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("Bucle de reintentos termino de forma inesperada.")


class YouTubeClient:
    """Adaptador pequeno sobre el cliente oficial de Google."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        service: Any | None = None,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if service is None and not api_key:
            raise ValueError("Se requiere una clave API o un servicio inyectado.")
        self._service = service or build(
            "youtube", "v3", developerKey=api_key, cache_discovery=False
        )
        self._max_attempts = max_attempts
        self._sleep = sleep

    def search(self, **parameters: Any) -> dict[str, Any]:
        """Ejecuta `search.list` con reintentos seguros."""
        return execute_with_retry(
            lambda: self._service.search().list(**parameters).execute(),
            max_attempts=self._max_attempts,
            sleep=self._sleep,
        )

    def videos(self, **parameters: Any) -> dict[str, Any]:
        """Ejecuta `videos.list` con reintentos seguros."""
        return execute_with_retry(
            lambda: self._service.videos().list(**parameters).execute(),
            max_attempts=self._max_attempts,
            sleep=self._sleep,
        )

