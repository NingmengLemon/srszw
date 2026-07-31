"""M2 tests: VoicevoxClient, AudioQuery building, and CLI subcommands."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from srszw import (
    ChineseSynthesizer,
    SynthesisOptions,
    VoicevoxClient,
    build_audio_query,
)
from srszw.engine import EngineError, EngineHTTPError, EngineProtocolError

WAV_HEADER = b"RIFF\x00\x00\x00\x00WAVEfmt "


def make_client(handler) -> VoicevoxClient:
    """Build a VoicevoxClient over an httpx.MockTransport."""

    transport = httpx.MockTransport(handler)
    return VoicevoxClient(
        "http://engine.test", client=httpx.Client(transport=transport)
    )


def test_version_and_speakers_round_trip() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return httpx.Response(200, json="0.25.2")
        if request.url.path == "/speakers":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "ずんだもん",
                        "speaker_uuid": "uuid-1",
                        "styles": [{"name": "ノーマル", "id": 3, "type": "talk"}],
                        "version": "0.25.2",
                    }
                ],
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    with make_client(handler) as client:
        assert client.version() == "0.25.2"
        speakers = client.speakers()
        assert speakers[0]["styles"][0]["id"] == 3


def test_synthesis_posts_snake_case_query_and_returns_wav() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, content=WAV_HEADER + b"\x00" * 64)

    with make_client(handler) as client:
        synthesizer = ChineseSynthesizer(client, seed=9)
        wav = synthesizer.synthesize("你好。", speaker=3)

    assert wav.startswith(b"RIFF")
    assert "speaker=3" in str(captured["url"])
    body = captured["body"]
    assert isinstance(body, dict)
    assert "accent_phrases" in body
    assert "speedScale" in body
    assert body["outputSamplingRate"] == 24000
    first_mora = body["accent_phrases"][0]["moras"][0]
    assert "consonant_length" in first_mora
    assert "vowel_length" in first_mora
    assert "pause_mora" in body["accent_phrases"][1]


def test_build_audio_query_is_engine_ready() -> None:
    query = build_audio_query("你好，世界！", SynthesisOptions(speed_scale=1.2), seed=2)

    assert query["speedScale"] == 1.2
    assert query["accent_phrases"]
    assert "pauseLength" in query
    assert query["outputStereo"] is False


def test_engine_http_error_has_context() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text='{"detail":"bad"}')

    with make_client(handler) as client:
        with pytest.raises(EngineHTTPError) as exc_info:
            client.synthesis(build_audio_query("你好", seed=1), speaker=3)
    assert exc_info.value.response.status_code == 422


def test_engine_connection_error_wraps_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with make_client(handler) as client:
        with pytest.raises(EngineError):
            client.version()


def test_synthesize_to_file_creates_wav(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=WAV_HEADER + b"\x01" * 32)

    with make_client(handler) as client:
        synthesizer = ChineseSynthesizer(client, seed=4)
        output_path = synthesizer.synthesize_to_file(
            "你好。",
            3,
            tmp_path / "audio" / "hello.wav",
        )

    assert output_path.read_bytes().startswith(b"RIFF")


def test_invalid_json_response_becomes_protocol_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not JSON")

    with make_client(handler) as client:
        with pytest.raises(EngineProtocolError, match="/version 返回了无效 JSON"):
            client.version()


def test_cli_query_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    from srszw.cli import run_subcommand

    assert run_subcommand(["query", "--text", "你好", "--seed", "6"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["accent_phrases"]


def test_cli_synthesize_writes_wav_and_protects_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from srszw import cli

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=WAV_HEADER + b"\x02" * 32)

    output = tmp_path / "cli.wav"
    with make_client(handler) as client:
        monkeypatch.setattr(cli, "_new_client", lambda _: client)
        assert (
            cli.run_subcommand(
                [
                    "synthesize",
                    "--text",
                    "你好。",
                    "--speaker",
                    "3",
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        assert output.read_bytes().startswith(b"RIFF")

        assert (
            cli.run_subcommand(
                [
                    "synthesize",
                    "--text",
                    "你好。",
                    "--speaker",
                    "3",
                    "--output",
                    str(output),
                ]
            )
            == 1
        )

    assert "如需覆盖请使用 --force" in capsys.readouterr().err


def test_cli_synthesize_reads_utf8_text_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from srszw import cli

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=WAV_HEADER + b"\x03" * 32)

    text_file = tmp_path / "input.txt"
    text_file.write_text("你好。", encoding="utf-8")
    output = tmp_path / "file-input.wav"
    with make_client(handler) as client:
        monkeypatch.setattr(cli, "_new_client", lambda _: client)
        assert (
            cli.run_subcommand(
                [
                    "synthesize",
                    "--text-file",
                    str(text_file),
                    "--speaker",
                    "3",
                    "--output",
                    str(output),
                ]
            )
            == 0
        )

    assert output.read_bytes().startswith(b"RIFF")


@pytest.mark.integration
def test_real_engine_end_to_end() -> None:
    """Optional live test against VVENGINE_URL (e.g. the local 50021)."""

    engine_url = os.environ.get("VVENGINE_URL")
    if not engine_url:
        pytest.skip("VVENGINE_URL 未设置，跳过真实 Engine 集成测试")

    with VoicevoxClient(engine_url) as client:
        version = client.version()
        speakers = client.speakers()
        style_ids = [style["id"] for speaker in speakers for style in speaker["styles"]]
        speaker = style_ids[0] if style_ids else 2
        synthesizer = ChineseSynthesizer(client, seed=7)
        wav = synthesizer.synthesize("你好，世界。", speaker=speaker)

    assert version
    assert wav.startswith(b"RIFF")
    assert len(wav) > 44
