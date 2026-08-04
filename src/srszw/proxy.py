"""Optional VOICEVOX-compatible reverse proxy with targeted Mandarin patches.

The proxy deliberately has no import-time dependency on Starlette or Uvicorn so
ordinary library users do not need the ``proxy`` extra.  In ``auto`` mode it
only replaces the text-analysis responses for clearly Mandarin input; synthesis
and every unrecognised endpoint remain transparent HTTP pass-throughs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal
from unicodedata import name as unicode_name

import httpx

from .api import build_audio_query
from .srszw_core import ConversionError

__all__ = [
    "ProxyConfig",
    "ProxyDependencyError",
    "create_proxy_app",
    "parse_listen_address",
    "run_proxy",
]

ProxyMode = Literal["auto", "off", "force"]
_PATCHABLE_PATHS = frozenset({"/audio_query", "/accent_phrases"})
_HOP_BY_HOP_HEADERS = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
    }
)
_ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


class ProxyDependencyError(RuntimeError):
    """Raised when the optional proxy dependencies are not installed."""


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    """Configuration for a single-upstream VOICEVOX HTTP proxy.

    ``max_body_bytes`` limits buffered request bodies. Responses are streamed,
    avoiding an in-memory copy of WAV and other binary Engine responses.
    """

    upstream_url: str = "http://127.0.0.1:50021"
    mode: ProxyMode = "auto"
    timeout: float = 30.0
    max_body_bytes: int = 16 * 1024 * 1024
    seed: int | None = 0

    def __post_init__(self) -> None:
        url = httpx.URL(self.upstream_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("upstream_url 必须是包含主机的 HTTP(S) URL")
        if url.query or url.fragment:
            raise ValueError("upstream_url 不能包含查询参数或片段")
        if self.mode not in {"auto", "off", "force"}:
            raise ValueError(f"不支持的代理模式: {self.mode!r}")
        if self.timeout <= 0:
            raise ValueError("代理 timeout 必须大于零")
        if self.max_body_bytes <= 0:
            raise ValueError("代理 max_body_bytes 必须大于零")
        object.__setattr__(self, "upstream_url", str(url).rstrip("/"))


def _require_proxy_dependencies() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    """Load ASGI dependencies lazily and explain how to install them."""

    try:
        from starlette.applications import Starlette
        from starlette.background import BackgroundTask
        from starlette.middleware.cors import CORSMiddleware
        from starlette.requests import Request
        from starlette.responses import JSONResponse, Response, StreamingResponse
        from starlette.routing import Route
    except ImportError as error:
        raise ProxyDependencyError(
            "反向代理需要可选依赖；请安装 `srszw[proxy]`，"
            "或在源码仓库运行 `uv sync --extra proxy`"
        ) from error
    return (
        Starlette,
        BackgroundTask,
        CORSMiddleware,
        Request,
        JSONResponse,
        Response,
        StreamingResponse,
        Route,
    )


def _is_han(character: str) -> bool:
    """Return whether a Unicode character is a CJK ideograph.

    Japanese kanji and Chinese Hanzi are inherently ambiguous.  ``auto`` mode
    therefore leaves text containing Hiragana or Katakana alone, while a
    Japanese all-kanji string may require ``--mode off`` from the caller.
    """

    return unicode_name(character, "").startswith(
        ("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")
    )


def _looks_like_mandarin(text: str) -> bool:
    """Conservatively classify text for the proxy's automatic patch mode."""

    has_han = any(_is_han(character) for character in text)
    has_japanese_kana = any(
        "\u3040" <= character <= "\u30ff" for character in text
    )
    return has_han and not has_japanese_kana


def _is_true(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _should_patch(request: Any, config: ProxyConfig) -> bool:
    """Whether a request is one of the two narrowly scoped local patches."""

    if config.mode == "off" or request.method != "POST":
        return False
    if request.url.path not in _PATCHABLE_PATHS:
        return False
    text = request.query_params.get("text")
    if text is None or _is_true(request.query_params.get("is_kana")):
        return False
    return config.mode == "force" or _looks_like_mandarin(text)


def _filtered_headers(
    headers: Iterable[tuple[bytes, bytes]], *, request_headers: bool
) -> list[tuple[bytes, bytes]]:
    """Remove hop-by-hop headers while retaining end-to-end header duplicates."""

    raw_headers = list(headers)
    connection_values = [
        value for key, value in raw_headers if key.lower() == b"connection"
    ]
    connection_tokens = {
        token.strip().lower()
        for value in connection_values
        for token in value.split(b",")
        if token.strip()
    }
    excluded = _HOP_BY_HOP_HEADERS | connection_tokens
    if request_headers:
        excluded = excluded | {b"host"}
    return [(key, value) for key, value in raw_headers if key.lower() not in excluded]


def _header_pairs_for_httpx(
    headers: Iterable[tuple[bytes, bytes]],
) -> list[tuple[str, str]]:
    """Convert raw ASGI headers without altering their byte representation."""

    return [
        (key.decode("latin-1"), value.decode("latin-1")) for key, value in headers
    ]


def _upstream_url(request: Any, config: ProxyConfig) -> str:
    """Build the upstream URL while retaining the requested path and query."""

    url = f"{config.upstream_url}{request.url.path}"
    if request.url.query:
        return f"{url}?{request.url.query}"
    return url


def _response_from_buffer(
    upstream_response: httpx.Response, response_type: Any
) -> Any:
    """Return a buffered proxy response with upstream status and headers."""

    response = response_type(
        upstream_response.content,
        status_code=upstream_response.status_code,
    )
    response.raw_headers = _filtered_headers(
        upstream_response.headers.raw, request_headers=False
    )
    return response


def _error_response(json_response_type: Any, detail: str, status_code: int) -> Any:
    return json_response_type({"detail": detail}, status_code=status_code)


async def _read_limited_body(request: Any, max_body_bytes: int) -> bytes:
    """Read a request body while enforcing the proxy's body-size limit."""

    chunks: list[bytes] = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > max_body_bytes:
            raise ValueError("请求体超过代理允许的最大大小")
        chunks.append(chunk)
    return b"".join(chunks)


def create_proxy_app(
    config: ProxyConfig | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Any:
    """Create the optional ASGI proxy application.

    ``transport`` is intentionally injectable for deterministic tests.  Normal
    callers should omit it so HTTPX connects to ``config.upstream_url``.
    """

    (
        Starlette,
        _BackgroundTask,
        CORSMiddleware,
        _Request,
        JSONResponse,
        Response,
        StreamingResponse,
        Route,
    ) = _require_proxy_dependencies()
    del _BackgroundTask, _Request
    config = config or ProxyConfig()

    @asynccontextmanager
    async def lifespan(_: Any) -> AsyncIterator[dict[str, httpx.AsyncClient]]:
        async with httpx.AsyncClient(
            timeout=config.timeout,
            transport=transport,
            follow_redirects=False,
        ) as client:
            yield {"upstream_client": client}

    async def proxy_endpoint(request: Any) -> Any:
        client: httpx.AsyncClient = request.state.upstream_client
        url = _upstream_url(request, config)
        headers = _header_pairs_for_httpx(
            _filtered_headers(request.headers.raw, request_headers=True)
        )

        if _should_patch(request, config):
            declared_length = request.headers.get("content-length")
            if declared_length is not None:
                try:
                    if int(declared_length) > config.max_body_bytes:
                        return _error_response(
                            JSONResponse,
                            "请求体超过代理允许的最大大小",
                            413,
                        )
                except ValueError:
                    pass
            try:
                body = await _read_limited_body(request, config.max_body_bytes)
            except ValueError as error:
                return _error_response(JSONResponse, str(error), 413)
            text = request.query_params["text"]
            try:
                if request.url.path == "/accent_phrases":
                    return JSONResponse(
                        build_audio_query(text, seed=config.seed)["accent_phrases"]
                    )

                seed_response = await client.request(
                    request.method,
                    url,
                    headers=headers,
                    content=body,
                )
                try:
                    if seed_response.is_error:
                        return _response_from_buffer(seed_response, Response)
                    try:
                        seed_query = seed_response.json()
                    except ValueError:
                        seed_query = None
                    local_query = build_audio_query(text, seed=config.seed)
                    patched_query: dict[str, object] = dict(local_query)
                    if isinstance(seed_query, dict):
                        patched_query.update(seed_query)
                    patched_query["accent_phrases"] = local_query["accent_phrases"]
                    # The seed's kana represents the Engine's Japanese reading,
                    # not the locally generated Mandarin phoneme sequence.
                    patched_query["kana"] = local_query["kana"]
                    return JSONResponse(patched_query)
                finally:
                    await seed_response.aclose()
            except ConversionError as error:
                return _error_response(JSONResponse, str(error), 422)
            except httpx.RequestError:
                return _error_response(
                    JSONResponse,
                    "无法连接上游 VOICEVOX Engine",
                    502,
                )

        try:
            outgoing_request = client.build_request(
                request.method,
                url,
                headers=headers,
                content=request.stream(),
            )
            upstream_response = await client.send(outgoing_request, stream=True)
        except httpx.RequestError:
            return _error_response(JSONResponse, "无法连接上游 VOICEVOX Engine", 502)

        async def stream_upstream() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_response.aiter_raw():
                    yield chunk
            finally:
                await upstream_response.aclose()

        response = StreamingResponse(
            stream_upstream(),
            status_code=upstream_response.status_code,
        )
        response.raw_headers = _filtered_headers(
            upstream_response.headers.raw, request_headers=False
        )
        return response

    app = Starlette(
        routes=[Route("/{path:path}", proxy_endpoint, methods=_ALLOWED_METHODS)],
        lifespan=lifespan,
    )
    # VOICEVOX Desktop renderer requests originate from ``app://.``. The
    # upstream Engine's local-app CORS policy does not recognise a new proxy
    # port, so the proxy explicitly grants only that desktop origin.
    return CORSMiddleware(
        app,
        allow_origins=["app://."],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def parse_listen_address(value: str) -> tuple[str, int]:
    """Parse a ``HOST:PORT`` or ``[IPv6]:PORT`` listener address."""

    if value.startswith("["):
        host, separator, port_text = value[1:].partition("]:")
    else:
        host, separator, port_text = value.rpartition(":")
    if not separator or not host or not port_text:
        raise ValueError("--listen 必须为 HOST:PORT 或 [IPv6]:PORT")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("--listen 的端口必须是整数") from error
    if not 1 <= port <= 65535:
        raise ValueError("--listen 的端口必须在 1 到 65535 之间")
    return host, port


def run_proxy(
    *,
    listen: str,
    config: ProxyConfig,
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info",
) -> None:
    """Run the proxy server through the optional Uvicorn dependency."""

    try:
        import uvicorn
    except ImportError as error:
        raise ProxyDependencyError(
            "反向代理需要可选依赖；请安装 `srszw[proxy]`，"
            "或在源码仓库运行 `uv sync --extra proxy`"
        ) from error

    host, port = parse_listen_address(listen)
    uvicorn.run(create_proxy_app(config), host=host, port=port, log_level=log_level)
