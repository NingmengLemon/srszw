"""Typed models matching the VOICEVOX Engine HTTP (snake_case) contract.

The Engine 0.25.2 OpenAPI document uses snake_case field names on the wire:
``accent_phrases``, ``pause_mora``, ``consonant_length`` and ``vowel_length``.
These models are serialised directly with ``dict()`` and do not round-trip the
camelCase VVProj document produced by the offline converter.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class Mora(TypedDict, total=False):
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


class AccentPhrase(TypedDict, total=False):
    """An accent phrase inside an Engine AudioQuery."""

    moras: list[Mora]
    accent: int
    pause_mora: PauseMora | None
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
