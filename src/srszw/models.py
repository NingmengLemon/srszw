"""Typed models matching the VOICEVOX Engine HTTP (snake_case) contract.

The Engine 0.25.2 OpenAPI document uses snake_case field names on the wire:
``accent_phrases``, ``pause_mora``, ``consonant_length`` and ``vowel_length``.
These models are serialised directly with ``dict()`` and do not round-trip the
camelCase VVProj document produced by the offline converter.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal, NotRequired, TypedDict


class Mora(TypedDict):
    """A single mora, as POSTed to and returned by the Engine."""

    text: str
    consonant: str | None
    consonant_length: float | None
    vowel: str
    vowel_length: float
    pitch: NotRequired[float]


class PauseMora(TypedDict):
    """A VOICEVOX pause mora."""

    text: str
    vowel: str
    vowel_length: float
    pitch: float


class AccentPhrase(TypedDict):
    """An accent phrase inside an Engine AudioQuery."""

    moras: list[Mora]
    accent: int
    pause_mora: NotRequired[PauseMora]
    is_interrogative: bool


class AudioQuery(TypedDict):
    """The Engine's AudioQuery request/response body.

    The top level of the Engine contract mixes naming styles: parameter fields
    are camelCase (``speedScale``, ``prePhonemeLength``) while the nested
    accent-phrase structures use snake_case (``accent_phrases``,
    ``consonant_length``).
    """

    accent_phrases: list[AccentPhrase]
    speedScale: float
    pitchScale: float
    intonationScale: float
    volumeScale: float
    prePhonemeLength: float
    postPhonemeLength: float
    pauseLength: float | None
    pauseLengthScale: float
    outputSamplingRate: int
    outputStereo: bool
    kana: str


@dataclass(frozen=True)
class SynthesisOptions:
    """Voice parameters shared by direct synthesis and VVProj export."""

    speed_scale: float = 1.0
    pitch_scale: float = 0.0
    intonation_scale: float = 1.0
    volume_scale: float = 1.0
    pre_phoneme_length: float = 0.1
    post_phoneme_length: float = 0.1
    pause_length_scale: float = 1.0
    output_sampling_rate: int = 24000
    output_stereo: bool = False

    def __post_init__(self) -> None:
        """Reject invalid values before a malformed query reaches the Engine."""

        numeric_fields = {
            "speed_scale": self.speed_scale,
            "pitch_scale": self.pitch_scale,
            "intonation_scale": self.intonation_scale,
            "volume_scale": self.volume_scale,
            "pre_phoneme_length": self.pre_phoneme_length,
            "post_phoneme_length": self.post_phoneme_length,
            "pause_length_scale": self.pause_length_scale,
        }
        for name, value in numeric_fields.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{name} 必须是数值")
            if not isfinite(value):
                raise ValueError(f"{name} 必须是有限数值")
        for name in (
            "speed_scale",
            "intonation_scale",
            "volume_scale",
            "pre_phoneme_length",
            "post_phoneme_length",
            "pause_length_scale",
        ):
            if numeric_fields[name] < 0:
                raise ValueError(f"{name} 不能为负数")
        if isinstance(self.output_sampling_rate, bool) or not isinstance(
            self.output_sampling_rate, int
        ):
            raise ValueError("output_sampling_rate 必须是整数")
        if self.output_sampling_rate <= 0:
            raise ValueError("output_sampling_rate 必须大于零")
        if not isinstance(self.output_stereo, bool):
            raise ValueError("output_stereo 必须是布尔值")

    def as_engine_query_fields(self) -> dict[str, Any]:
        """Return the non-accent fields expected by an Engine AudioQuery."""

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


class StyleInfo(TypedDict):
    """A speaker style within a Voicevox Speaker."""

    name: str
    id: int
    type: Literal["talk", "frame", "sing"]


class SupportedFeatures(TypedDict, total=False):
    """Per-speaker feature flags returned by ``/speakers``."""

    adjust_mora_pitch: bool
    adjust_phoneme_length: bool
    adjust_speed_scale: bool
    adjust_pitch_scale: bool
    adjust_intonation_scale: bool
    adjust_volume_scale: bool
    adjust_pause_length: bool
    interrogative_upspeak: bool
    synthesis_morphing: bool
    sing: bool
    manage_library: bool
    return_resource_url: bool
    apply_katakana_english: bool


class Speaker(TypedDict):
    """A speaker entry returned by ``/speakers``."""

    name: str
    speaker_uuid: str
    styles: list[StyleInfo]
    version: str
    supported_features: NotRequired[SupportedFeatures]


# Structural aliases used by the public Engine client.
Speakers = list[Speaker]
