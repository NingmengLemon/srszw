"""Tests for the optional Mandarin-compatible VOICEVOX reverse proxy."""

from __future__ import annotations

import json

import httpx

from srszw import build_audio_query
from srszw.proxy import ProxyConfig, create_proxy_app, parse_listen_address

_PROXY_SEED = 0


WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 48


class _BytesStream(httpx.AsyncByteStream):
    """An unread async stream, unlike the eager HTTPX MockTransport stream."""

    def __init__(self, content: bytes) -> None:
        self._content = content

    async def __aiter__(self):
        yield self._content


class _HandlerTransport(httpx.AsyncBaseTransport):
    """Adapt a synchronous assertion handler to a non-eager async transport."""

    def __init__(self, handler) -> None:
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        content = await request.aread()
        buffered_request = httpx.Request(
            request.method,
            request.url,
            headers=request.headers,
            content=content,
        )
        response = self._handler(buffered_request)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=_BytesStream(response.content),
            request=request,
        )



def make_client(
    handler, *, mode: str = "auto", max_body_bytes: int = 16 * 1024 * 1024
):
    """Return a Starlette client backed by a deterministic upstream transport."""

    from starlette.testclient import TestClient

    app = create_proxy_app(
        ProxyConfig(
            upstream_url="http://engine.test",
            mode=mode,  # type: ignore[arg-type]
            max_body_bytes=max_body_bytes,
        ),
        transport=_HandlerTransport(handler),
    )
    return TestClient(app)


def test_auto_mode_patches_chinese_accent_phrases_without_upstream_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected upstream request: {request.url}")

    with make_client(handler) as client:
        response = client.post(
            "/accent_phrases",
            params={"text": "你好，世界！", "speaker": 2},
        )

    assert response.status_code == 200
    phrases = response.json()
    assert phrases == build_audio_query("你好，世界！", seed=_PROXY_SEED)[
        "accent_phrases"
    ]
    assert "pause_mora" in phrases[1]


def test_audio_query_merges_engine_defaults_and_replaces_chinese_prosody() -> None:
    captured: dict[str, object] = {}
    engine_query = {
        "accent_phrases": [{"moras": [], "accent": 1, "is_interrogative": False}],
        "speedScale": 1.3,
        "pitchScale": -0.1,
        "intonationScale": 0.8,
        "volumeScale": 0.7,
        "prePhonemeLength": 0.2,
        "postPhonemeLength": 0.3,
        "pauseLength": 0.4,
        "pauseLengthScale": 0.9,
        "outputSamplingRate": 44100,
        "outputStereo": True,
        "kana": "ニホンゴ",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json=engine_query)

    with make_client(handler) as client:
        response = client.post(
            "/audio_query",
            params={"text": "你好。", "speaker": 2, "core_version": "0.25.2"},
        )

    assert response.status_code == 200
    query = response.json()
    expected = build_audio_query("你好。", seed=_PROXY_SEED)
    assert captured["method"] == "POST"
    assert "core_version=0.25.2" in str(captured["url"])
    assert query["speedScale"] == 1.3
    assert query["outputSamplingRate"] == 44100
    assert query["accent_phrases"] == expected["accent_phrases"]
    assert query["kana"] == ""


def test_auto_mode_preserves_japanese_audio_query_response() -> None:
    engine_query = {"kana": "コンニチワ", "accent_phrases": []}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/audio_query"
        assert request.url.params["text"] == "こんにちは"
        return httpx.Response(200, json=engine_query, headers={"x-engine": "direct"})

    with make_client(handler) as client:
        response = client.post(
            "/audio_query",
            params={"text": "こんにちは", "speaker": 2},
        )

    assert response.status_code == 200
    assert response.json() == engine_query
    assert response.headers["x-engine"] == "direct"


def test_proxy_streams_synthesis_and_preserves_unknown_request_details() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = list(request.url.params.multi_items())
        captured["content"] = request.content
        captured["header"] = request.headers["x-trace-id"]
        return httpx.Response(
            206,
            content=WAV,
            headers={"content-type": "audio/wav", "x-upstream": "yes"},
        )

    body = json.dumps({"accent_phrases": []}).encode()
    with make_client(handler) as client:
        response = client.post(
            "/synthesis?speaker=2&speaker=3",
            content=body,
            headers={"content-type": "application/json", "x-trace-id": "audit-1"},
        )

    assert response.status_code == 206
    assert response.content == WAV
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["x-upstream"] == "yes"
    assert captured == {
        "method": "POST",
        "path": "/synthesis",
        "params": [("speaker", "2"), ("speaker", "3")],
        "content": body,
        "header": "audit-1",
    }


def test_off_mode_forwards_chinese_text_unchanged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": request.url.params["text"]})

    with make_client(handler, mode="off") as client:
        response = client.post(
            "/accent_phrases",
            params={"text": "你好", "speaker": 2},
        )

    assert response.status_code == 200
    assert response.json() == {"text": "你好"}


def test_proxy_returns_502_when_upstream_connection_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with make_client(handler) as client:
        response = client.get("/version")

    assert response.status_code == 502
    assert response.json() == {"detail": "无法连接上游 VOICEVOX Engine"}


def test_proxy_does_not_apply_buffer_limit_to_transparent_requests() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(200, content=b"ok")

    with make_client(handler, max_body_bytes=3) as client:
        response = client.post("/synthesis", content=b"1234")

    assert response.status_code == 200
    assert response.content == b"ok"
    assert captured["content"] == b"1234"


def test_proxy_rejects_oversized_patched_request_before_upstream_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected upstream request: {request.url}")

    with make_client(handler, max_body_bytes=3) as client:
        response = client.post(
            "/audio_query",
            params={"text": "你好", "speaker": 2},
            content=b"1234",
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "请求体超过代理允许的最大大小"}


def test_parse_listen_address_accepts_ipv4_and_ipv6() -> None:
    assert parse_listen_address("127.0.0.1:50022") == ("127.0.0.1", 50022)
    assert parse_listen_address("[::1]:50022") == ("::1", 50022)
