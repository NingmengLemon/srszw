"""Synchronous VOICEVOX Engine HTTP client built on :mod:`httpx`.

The client targets the Engine HTTP API as documented by its OpenAPI document;
it performs no Chinese conversion itself.  Combine it with
:func:`srszw.generate_accent_phrases` through ``ChineseSynthesizer``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from httpx import RequestError

from .models import AudioQuery, Speakers

__all__ = [
    "EngineError",
    "EngineHTTPError",
    "EngineProtocolError",
    "VoicevoxClient",
]


class EngineError(Exception):
    """Base error for failures while talking to a VOICEVOX Engine."""


class EngineHTTPError(EngineError):
    """An Engine request completed with a non-2xx status code."""

    def __init__(
        self, message: str, *, request: httpx.Request, response: httpx.Response
    ) -> None:
        self.request = request
        self.response = response
        super().__init__(message)


class EngineProtocolError(EngineError):
    """An Engine response did not follow the documented response schema."""


class VoicevoxClient:
    """Thin synchronous client over a single VOICEVOX Engine base URL.

    Args:
        base_url: Engine base URL, e.g. ``http://127.0.0.1:50021``.
        timeout: Request timeout in seconds.
        client: Optional pre-configured :class:`httpx.Client`; when omitted a
            private client is created and closed with the instance.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._owned_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def client(self) -> httpx.Client:
        """The underlying :class:`httpx.Client`."""

        return self._client

    def close(self) -> None:
        """Close the owned HTTP client."""

        if self._owned_client:
            self._client.close()

    def __enter__(self) -> VoicevoxClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        try:
            response = self._client.request(method, url, params=params, json=json)
        except RequestError as error:
            raise EngineError(f"无法连接到 VOICEVOX Engine: {error}") from error
        if response.is_error:
            detail = response.text[:400] if response.text else ""
            raise EngineHTTPError(
                f"VOICEVOX Engine 返回 {response.status_code}: {detail}",
                request=response.request,
                response=response,
            )
        return response

    @staticmethod
    def _json(response: httpx.Response, endpoint: str) -> object:
        """Decode a JSON response and expose protocol failures as Engine errors."""

        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise EngineProtocolError(
                f"{endpoint} 返回了无效 JSON: {error}"
            ) from error

    def version(self) -> str:
        """Return the Engine version string from ``/version``."""

        response = self._request("GET", "/version")
        data = self._json(response, "/version")
        if not isinstance(data, str):
            raise EngineError(f"/version 返回了非字符串结果: {data!r}")
        return data

    def speakers(self) -> Speakers:
        """Return the Engine's current speaker/style catalog from ``/speakers``."""

        response = self._request("GET", "/speakers")
        data = self._json(response, "/speakers")
        if not isinstance(data, list):
            raise EngineError("/speakers 必须返回 JSON 数组")
        return data  # type: ignore[return-value]

    def speaker_info(self, speaker: int) -> dict[str, Any]:
        """Return rich speaker metadata from ``/speaker_info``."""

        response = self._request("GET", "/speaker_info", params={"speaker": speaker})
        data = self._json(response, "/speaker_info")
        if not isinstance(data, dict):
            raise EngineError("/speaker_info 必须返回 JSON 对象")
        return data

    def synthesis(self, query: AudioQuery, speaker: int) -> bytes:
        """POST an AudioQuery to ``/synthesis`` and return the WAV bytes."""

        response = self._request(
            "POST",
            "/synthesis",
            params={"speaker": speaker},
            json=dict(query),
        )
        content = response.content
        if not content:
            raise EngineError("/synthesis 返回了空响应体")
        return content

    def audio_query(self, text: str, speaker: int) -> AudioQuery:
        """Ask the Engine for its own AudioQuery for Japanese text."""

        response = self._request(
            "POST",
            "/audio_query",
            params={"text": text, "speaker": speaker},
        )
        data = self._json(response, "/audio_query")
        if not isinstance(data, dict):
            raise EngineError("/audio_query 必须返回 JSON 对象")
        return data  # type: ignore[return-value]
