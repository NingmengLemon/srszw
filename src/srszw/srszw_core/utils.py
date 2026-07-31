"""Legacy VVProj helpers kept separate from the offline conversion API."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import Config
from .converter import SRSZWConverter

JsonObject = dict[str, Any]
PathLike = str | Path


def generate_from_string(
    text: str,
    charactor: str = "shikokumetan",
    style: str | None = None,
    config: Config | None = None,
    *,
    seed: int | None = None,
) -> JsonObject:
    """Generate a legacy VOICEVOX project for one text string.

    This compatibility helper retains the historical ``charactor`` parameter
    spelling. New code that only needs accent phrases should use
    :func:`srszw.generate_accent_phrases` instead.
    """

    return generate_from_strings([text], charactor, style, config, seed=seed)


def generate_from_strings(
    texts: Sequence[str],
    charactor: str = "shikokumetan",
    style: str | None = None,
    config: Config | None = None,
    *,
    seed: int | None = None,
) -> JsonObject:
    """Generate a legacy VOICEVOX project for multiple text strings."""

    project_data: JsonObject = {
        "script_version": "0.1",
        "app_version": "0.23.0",
        "talk": [
            {
                "charactor": charactor,
                "style": style,
                "speedScale": 1.0,
                "pitchScale": 0.0,
                "intonationScale": 1.0,
                "volumeScale": 1.0,
                "prePhonemeLength": 0.1,
                "postPhonemeLength": 0.1,
                "pauseLengthScale": 1.0,
                "text": {"pinyin": None, "zi": text},
            }
            for text in texts
        ],
    }
    return SRSZWConverter(config, seed=seed).convert(project_data)


def save_vvproj(vvproj_data: JsonObject, output_path: PathLike) -> Path:
    """Save a VVProj document, creating its parent directory when necessary."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(vvproj_data, file, ensure_ascii=False, indent=2)
    return path


def generate_and_save(
    text: str,
    output_path: PathLike,
    charactor: str = "shikokumetan",
    style: str | None = None,
    config: Config | None = None,
    *,
    seed: int | None = None,
) -> Path:
    """Generate and save a legacy VOICEVOX project for one text string."""

    return save_vvproj(
        generate_from_string(text, charactor, style, config, seed=seed), output_path
    )


def load_project_file(project_path: PathLike) -> JsonObject:
    """Load and validate the top-level shape of a legacy SRSZW project file."""

    path = Path(project_path)
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"项目文件必须是 JSON 对象: {path}")
    return data


def convert_project_file(
    input_path: PathLike,
    output_path: PathLike,
    config: Config | None = None,
    *,
    seed: int | None = None,
) -> Path:
    """Convert a legacy SRSZW project file to a VVProj file."""

    vvproj_data = SRSZWConverter(config, seed=seed).convert(
        load_project_file(input_path)
    )
    return save_vvproj(vvproj_data, output_path)
