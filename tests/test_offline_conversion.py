"""Regression tests for M0/M1 offline conversion behaviour."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from srszw import Config, ConversionError, generate_accent_phrases
from srszw.main import main
from srszw.srszw_core.utils import generate_and_save


def test_bundled_resources_work_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default conversion must not depend on the source checkout's CWD."""

    monkeypatch.chdir(tmp_path)

    config = Config()
    phrases = generate_accent_phrases("你好。", config=config, seed=7)

    assert config.kana["i"] == "イ"
    assert len(phrases) == 2
    assert phrases[-1]["pauseMora"]["vowel"] == "pau"


def test_seed_makes_conversion_reproducible() -> None:
    """A seed fixes all optional pitch and duration variation."""

    first = generate_accent_phrases("你好，世界！", seed=42)
    second = generate_accent_phrases("你好，世界！", seed=42)
    different_seed = generate_accent_phrases("你好，世界！", seed=43)

    assert first == second
    assert first != different_seed


def test_large_duration_randomness_never_creates_nonpositive_moras() -> None:
    """Custom legacy randomness must not yield invalid Engine durations."""

    phrases = generate_accent_phrases("你好。", config=Config(lengthRandom=1.0), seed=1)
    lengths = [
        mora["vowelLength"]
        for phrase in phrases
        for mora in phrase["moras"]
    ]
    lengths.extend(
        phrase["pauseMora"]["vowelLength"]
        for phrase in phrases
        if "pauseMora" in phrase
    )

    assert all(length > 0 for length in lengths)


def test_punctuation_adds_pause_to_preceding_phrase() -> None:
    """Chinese punctuation should become a pause without creating a phrase."""

    phrases = generate_accent_phrases("你好，世界！", seed=1)

    assert len(phrases) == 4
    assert "pauseMora" not in phrases[0]
    assert phrases[1]["pauseMora"]["text"] == "、"
    assert "pauseMora" not in phrases[2]
    assert phrases[3]["pauseMora"]["pitch"] == 0


def test_invalid_input_has_actionable_error() -> None:
    """Unsupported text must not silently become a malformed query."""

    with pytest.raises(ConversionError, match="不支持的文本片段"):
        generate_accent_phrases("hello")

    with pytest.raises(ConversionError, match="文本不能为空"):
        generate_accent_phrases(" \t\n")


def test_legacy_config_paths_are_relative_to_config_file(tmp_path: Path) -> None:
    """Legacy path-based configs retain intuitive relative-path behaviour."""

    config_path = tmp_path / "settings" / "srszw.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "file": "input.hooay-srszw.json",
                "output": "output/result.vvproj",
                "loaded_charactor_lists": [],
                "pitchRange": [4.5, 6.0],
            }
        ),
        encoding="utf-8",
    )

    config = Config.from_file(config_path)

    assert config.file == config_path.parent / "input.hooay-srszw.json"
    assert config.output == config_path.parent / "output" / "result.vvproj"
    assert config.pitchRange == (4.5, 6.0)
    assert config.kana["N"] == "ン"


def test_legacy_project_export_creates_parent_directory(tmp_path: Path) -> None:
    """The compatibility export helper still creates an editable VVProj."""

    output_path = generate_and_save(
        "你好。",
        tmp_path / "nested" / "hello.vvproj",
        seed=3,
    )
    document = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.exists()
    assert document["appVersion"] == "0.23.0"
    assert len(document["talk"]["audioKeys"]) == 1


def test_cli_text_export_is_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transitional CLI accepts a seed and produces the requested file."""

    monkeypatch.chdir(tmp_path)
    output_path = Path("generated") / "hello.vvproj"

    assert main(["--text", "你好。", "--output", str(output_path), "--seed", "5"]) == 0
    first_output = output_path.read_text(encoding="utf-8")
    assert main(["--text", "你好。", "--output", str(output_path), "--seed", "5"]) == 0

    assert output_path.read_text(encoding="utf-8") == first_output
