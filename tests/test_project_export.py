"""M3 tests: versioned VVProj export through Python API and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from srszw import (
    ChineseSynthesizer,
    ProjectExportError,
    ProjectUtterance,
    SynthesisOptions,
)
from srszw.engine import VoicevoxClient
from srszw.project import VVProjExporter, to_vvproj_query

ENGINE_UUID = "074fc39e-678b-4c13-8916-ffca8d505d1d"
SPEAKER_UUIDS = {2: "speaker-metan", 3: "speaker-zundamon"}


def make_project_client() -> VoicevoxClient:
    """Create an Engine client with the discovery endpoints used by export."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/engine_manifest":
            return httpx.Response(200, json={"uuid": ENGINE_UUID})
        if request.url.path == "/speakers":
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "四国めたん",
                        "speaker_uuid": SPEAKER_UUIDS[2],
                        "styles": [
                            {"name": "ノーマル", "id": 2, "type": "talk"},
                        ],
                        "version": "0.25.2",
                    },
                    {
                        "name": "ずんだもん",
                        "speaker_uuid": SPEAKER_UUIDS[3],
                        "styles": [
                            {"name": "ノーマル", "id": 3, "type": "talk"},
                        ],
                        "version": "0.25.2",
                    },
                ],
            )
        raise AssertionError(f"unexpected request: {request.url}")

    return VoicevoxClient(
        "http://engine.test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_export_project_reuses_the_direct_tts_query_path(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "project.vvproj"
    override_options = SynthesisOptions(speed_scale=1.2, output_sampling_rate=48000)
    utterances = [
        ProjectUtterance("你好。"),
        ProjectUtterance("世界！", speaker=3, options=override_options),
    ]

    with make_project_client() as client:
        synthesizer = ChineseSynthesizer(client, seed=8)
        result = synthesizer.export_project(utterances, output, speaker=2)
        document = json.loads(result.read_text(encoding="utf-8"))

        first_key, second_key = document["talk"]["audioKeys"]
        first = document["talk"]["audioItems"][first_key]
        second = document["talk"]["audioItems"][second_key]
        assert first["voice"] == {
            "engineId": ENGINE_UUID,
            "speakerId": SPEAKER_UUIDS[2],
            "styleId": 2,
        }
        assert second["voice"] == {
            "engineId": ENGINE_UUID,
            "speakerId": SPEAKER_UUIDS[3],
            "styleId": 3,
        }
        assert first["query"] == to_vvproj_query(synthesizer.prepare_query("你好。"))
        assert second["query"] == to_vvproj_query(
            synthesizer.prepare_query("世界！", override_options)
        )

    assert document["appVersion"] == "0.25.2"
    assert list(document["talk"]["audioItems"]) == document["talk"]["audioKeys"]
    track_key = document["song"]["trackOrder"][0]
    track = document["song"]["tracks"][track_key]
    assert track["volumeEditData"] == []
    assert track["phonemeTimingEditData"] == {}
    assert track["notes"] == []


def test_export_is_reproducible_when_seeded(tmp_path: Path) -> None:
    with make_project_client() as client:
        synthesizer = ChineseSynthesizer(client, seed=42)
        first = synthesizer.export_project(
            [ProjectUtterance("你好。")], tmp_path / "first.vvproj", speaker=2
        )
        second = synthesizer.export_project(
            [ProjectUtterance("你好。")], tmp_path / "second.vvproj", speaker=2
        )

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_export_rejects_unknown_project_schema_version() -> None:
    with pytest.raises(ProjectExportError, match="不支持导出 app_version"):
        VVProjExporter(app_version="0.26.0")


def test_cli_export_project_reads_multi_utterance_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from srszw import cli

    input_path = tmp_path / "utterances.json"
    input_path.write_text(
        json.dumps(
            [
                {"text": "你好。"},
                {
                    "text": "世界！",
                    "speaker": 3,
                    "options": {"speed_scale": 1.15},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "project.vvproj"
    with make_project_client() as client:
        monkeypatch.setattr(cli, "_new_client", lambda _: client)
        assert (
            cli.run_subcommand(
                [
                    "export-project",
                    "--input",
                    str(input_path),
                    "--speaker",
                    "2",
                    "--output",
                    str(output),
                    "--seed",
                    "11",
                ]
            )
            == 0
        )

    document = json.loads(output.read_text(encoding="utf-8"))
    audio_items = document["talk"]["audioItems"]
    second_key = document["talk"]["audioKeys"][1]
    assert audio_items[second_key]["voice"]["styleId"] == 3
    assert audio_items[second_key]["query"]["speedScale"] == 1.15


def test_cli_export_project_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from srszw import cli

    output = tmp_path / "existing.vvproj"
    output.write_text("original", encoding="utf-8")
    with make_project_client() as client:
        monkeypatch.setattr(cli, "_new_client", lambda _: client)
        assert (
            cli.run_subcommand(
                [
                    "export-project",
                    "--text",
                    "你好。",
                    "--speaker",
                    "2",
                    "--output",
                    str(output),
                ]
            )
            == 1
        )

    assert output.read_text(encoding="utf-8") == "original"
    assert "如需覆盖请使用 --force" in capsys.readouterr().err
