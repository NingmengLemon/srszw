"""High-level TTS orchestration: local Mandarin conversion + Engine synthesis.

The offline converter produces VVProj-style camelCase accent phrases; the
Engine HTTP contract requires snake_case field names.  ``ChineseSynthesizer``
bridges the two so callers only ever see stable public options.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .engine import VoicevoxClient
from .models import AccentPhrase, AudioQuery, Mora, PauseMora
from .srszw_core import Config
from .srszw_core.converter import SRSZWConverter

__all__ = [
    "ChineseSynthesizer",
    "SynthesisOptions",
    "build_audio_query",
    "to_engine_query",
]


@dataclass(frozen=True)
class SynthesisOptions:
    """Voice parameters shared by query preparation and synthesis."""

    speed_scale: float = 1.0
    pitch_scale: float = 0.0
    intonation_scale: float = 1.0
    volume_scale: float = 1.0
    pre_phoneme_length: float = 0.1
    post_phoneme_length: float = 0.1
    pause_length_scale: float = 1.0
    output_sampling_rate: int = 24000
    output_stereo: bool = False

    def as_engine_query_fields(self) -> dict[str, Any]:
        """Return the non-accent fields expected by the Engine AudioQuery."""

        return {
            "speedScale": self.speed_scale,
            "pitchScale": self.pitch_scale,
            "intonationScale": self.intonation_scale,
            "volumeScale": self.volume_scale,
            "prePhonemeLength": self.pre_phoneme_length,
            "postPhonemeLength": self.post_phoneme_length,
            "pauseLength": None,
            "pauseLengthScale": self.pause_length_scale,
            "outputSamplingRate": self.output_sampling_rate,
            "outputStereo": self.output_stereo,
            "kana": "",
        }


DEFAULT_OPTIONS = SynthesisOptions()


def _to_engine_mora(mora: dict[str, Any]) -> Mora:
    result: Mora = {
        "text": mora["text"],
        "consonant": mora.get("consonant"),
        "consonant_length": mora.get("consonantLength"),
        "vowel": mora["vowel"],
        "vowel_length": mora["vowelLength"],
    }
    if "pitch" in mora:
        result["pitch"] = mora["pitch"]
    return result


def _to_engine_accent_phrase(phrase: dict[str, Any]) -> AccentPhrase:
    result: AccentPhrase = {
        "moras": [_to_engine_mora(mora) for mora in phrase["moras"]],
        "accent": phrase["accent"],
        "is_interrogative": phrase["isInterrogative"],
    }
    pause_mora = phrase.get("pauseMora")
    if pause_mora is not None:
        result["pause_mora"] = PauseMora(
            text=pause_mora["text"],
            vowel=pause_mora["vowel"],
            vowel_length=pause_mora["vowelLength"],
            pitch=pause_mora["pitch"],
        )
    return result


def to_engine_query(accent_phrases: list[dict[str, Any]]) -> list[AccentPhrase]:
    """Convert offline camelCase accent phrases to Engine snake_case models."""

    return [_to_engine_accent_phrase(phrase) for phrase in accent_phrases]


def build_audio_query(
    text: str,
    options: SynthesisOptions = DEFAULT_OPTIONS,
    *,
    config: Config | None = None,
    seed: int | None = None,
) -> AudioQuery:
    """Build a complete Engine AudioQuery for Mandarin Chinese offline.

    Args:
        text: Chinese text to synthesize.
        options: Voice parameters.
        config: Optional conversion configuration (bundled tables by default).
        seed: Optional seed for reproducible pitch/duration variation.

    Returns:
        An Engine-compatible (snake_case) ``AudioQuery`` TypedDict.
    """

    converter = SRSZWConverter(config, seed=seed)
    fields = options.as_engine_query_fields()
    query: AudioQuery = {
        "accent_phrases": to_engine_query(converter.accent_phrases(text)),
        "speedScale": fields["speedScale"],
        "pitchScale": fields["pitchScale"],
        "intonationScale": fields["intonationScale"],
        "volumeScale": fields["volumeScale"],
        "prePhonemeLength": fields["prePhonemeLength"],
        "postPhonemeLength": fields["postPhonemeLength"],
        "pauseLength": fields["pauseLength"],
        "pauseLengthScale": fields["pauseLengthScale"],
        "outputSamplingRate": fields["outputSamplingRate"],
        "outputStereo": fields["outputStereo"],
        "kana": fields["kana"],
    }
    return query


class ChineseSynthesizer:
    """TTS facade: prepare Mandarin queries and request WAV bytes."""

    def __init__(
        self,
        client: VoicevoxClient,
        *,
        config: Config | None = None,
        seed: int | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._seed = seed

    def prepare_query(
        self,
        text: str,
        options: SynthesisOptions = DEFAULT_OPTIONS,
    ) -> AudioQuery:
        """Convert Mandarin text into an Engine-ready AudioQuery (offline)."""

        return build_audio_query(text, options, config=self._config, seed=self._seed)

    def synthesize(
        self,
        text: str,
        speaker: int,
        options: SynthesisOptions = DEFAULT_OPTIONS,
    ) -> bytes:
        """Synthesize Mandarin text and return the raw WAV bytes."""

        return self._client.synthesis(
            self.prepare_query(text, options),
            speaker=speaker,
        )

    def synthesize_to_file(
        self,
        text: str,
        speaker: int,
        output_path: str | Path,
        options: SynthesisOptions = DEFAULT_OPTIONS,
    ) -> Path:
        """Synthesize Mandarin text and write the WAV to ``output_path``."""

        wav_bytes = self.synthesize(text, speaker, options)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav_bytes)
        return path
