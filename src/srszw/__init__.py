"""SRSZW: offline Mandarin-to-VOICEVOX conversion and direct TTS.

Public entry points:

- :func:`generate_accent_phrases`: offline, VVProj-style accent phrases.
- :func:`build_audio_query`: offline, Engine-ready snake_case AudioQuery.
- :class:`VoicevoxClient` / :class:`ChineseSynthesizer`: talk to a running
  VOICEVOX Engine and produce WAV bytes or files.
"""

from __future__ import annotations

from typing import Any

from .api import ChineseSynthesizer, SynthesisOptions, build_audio_query
from .engine import EngineError, EngineHTTPError, EngineProtocolError, VoicevoxClient
from .models import AccentPhrase, AudioQuery, Mora, PauseMora, Speaker, Speakers
from .srszw_core import Config, ConversionError, SRSZWConverter

__version__ = "0.2.0"
__all__ = [
    "AccentPhrase",
    "AudioQuery",
    "ChineseSynthesizer",
    "Config",
    "ConversionError",
    "EngineError",
    "EngineHTTPError",
    "EngineProtocolError",
    "Mora",
    "PauseMora",
    "SRSZWConverter",
    "Speaker",
    "Speakers",
    "SynthesisOptions",
    "VoicevoxClient",
    "build_audio_query",
    "generate_accent_phrases",
]


def generate_accent_phrases(
    text: str,
    *,
    config: Config | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Convert Mandarin Chinese text to VVProj-style accent phrases offline.

    Args:
        text: Chinese text to convert. Punctuation adds a pause to the
            preceding accent phrase.
        config: Optional conversion configuration. Defaults use the data
            packaged with SRSZW and do not depend on the current directory.
        seed: Optional seed for reproducible timing and pitch variation.

    Returns:
        A list of JSON-serializable accent-phrase dictionaries using the
        camelCase keys required by the VVProj schema.

    Raises:
        ConversionError: If the input is empty or cannot be represented by
            the bundled Pinyin and phoneme tables.
    """

    return SRSZWConverter(config, seed=seed).accent_phrases(text)
