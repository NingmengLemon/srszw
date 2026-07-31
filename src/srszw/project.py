"""Versioned export of editable VOICEVOX project (``.vvproj``) files.

VOICEVOX project files deliberately use a different JSON shape from the Engine
HTTP API: accent phrase members are camelCase and every utterance carries an
Engine UUID, speaker UUID, and style ID. This module isolates that format from
the direct-TTS client while reusing :func:`srszw.api.build_audio_query` as its
single source of Mandarin prosody.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from .models import AudioQuery, SynthesisOptions

__all__ = [
    "ProjectExportError",
    "ProjectUtterance",
    "SUPPORTED_APP_VERSIONS",
    "VVProjExporter",
    "VoicevoxVoice",
    "to_vvproj_query",
]

JsonObject = dict[str, Any]

# VOICEVOX 0.25.2 is the local Engine/UI generation used to validate this
# initial exporter. New schemas must be added explicitly after inspecting their
# project-file migrations rather than guessed from a version number.
SUPPORTED_APP_VERSIONS = frozenset({"0.25.2"})


class ProjectExportError(ValueError):
    """Raised when an editable VOICEVOX project cannot be exported safely."""


@dataclass(frozen=True)
class VoicevoxVoice:
    """VOICEVOX voice identity required by a project audio item."""

    engine_id: str
    speaker_id: str
    style_id: int

    def __post_init__(self) -> None:
        if not self.engine_id:
            raise ProjectExportError("VOICEVOX Engine UUID 不能为空")
        if not self.speaker_id:
            raise ProjectExportError("VOICEVOX speaker UUID 不能为空")
        if self.style_id < 0:
            raise ProjectExportError("VOICEVOX style ID 不能为负数")


@dataclass(frozen=True)
class ProjectUtterance:
    """One editable talk item.

    ``speaker`` and ``options`` are optional per-item overrides. The exporter
    resolves missing values from its explicit defaults, allowing a project to
    use one shared voice/options set while overriding only selected utterances.
    """

    text: str
    speaker: int | None = None
    options: SynthesisOptions | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ProjectExportError("工程台词文本不能为空")
        if self.speaker is not None and self.speaker < 0:
            raise ProjectExportError("工程台词的 style ID 不能为负数")


@dataclass
class VVProjExporter:
    """Build a versioned VVProj document from offline conversion results.

    ``app_version`` determines the serialized schema. Unknown versions are
    refused so an Engine or UI upgrade never silently receives a guessed
    project format. ``seed`` makes generated object keys deterministic in
    addition to the pitch and duration variation handled by the converter.
    """

    app_version: str = "0.25.2"
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.app_version not in SUPPORTED_APP_VERSIONS:
            supported = ", ".join(sorted(SUPPORTED_APP_VERSIONS))
            raise ProjectExportError(
                f"不支持导出 app_version {self.app_version!r}；当前仅支持: {supported}"
            )
        self._key_index = 0

    def export(
        self,
        utterances: Sequence[ProjectUtterance],
        voices: Mapping[int, VoicevoxVoice],
        *,
        default_speaker: int | None,
        default_options: SynthesisOptions,
        build_query: Callable[[str, SynthesisOptions], AudioQuery],
    ) -> JsonObject:
        """Return a complete VVProj JSON document.

        ``default_speaker`` and ``default_options`` apply to an utterance when
        it does not explicitly supply its own values. A speaker must therefore
        be given either globally or on every project item.
        """

        if not utterances:
            raise ProjectExportError("工程至少需要一条台词")

        audio_keys: list[str] = []
        audio_items: JsonObject = {}
        for utterance in utterances:
            speaker = (
                utterance.speaker
                if utterance.speaker is not None
                else default_speaker
            )
            if speaker is None:
                raise ProjectExportError(
                    "每条工程台词都必须指定 style ID，或提供全局 speaker"
                )
            options = (
                utterance.options if utterance.options is not None else default_options
            )
            try:
                voice = voices[speaker]
            except KeyError as error:
                raise ProjectExportError(
                    f"Engine 未返回 style ID {speaker} 的角色信息"
                ) from error
            if voice.style_id != speaker:
                raise ProjectExportError(f"style ID {speaker} 的角色信息不一致")

            key = self._new_key()
            audio_keys.append(key)
            audio_items[key] = {
                "text": utterance.text,
                "voice": {
                    "engineId": voice.engine_id,
                    "speakerId": voice.speaker_id,
                    "styleId": voice.style_id,
                },
                "query": to_vvproj_query(
                    build_query(utterance.text, options)
                ),
            }

        return {
            "appVersion": self.app_version,
            "talk": {"audioKeys": audio_keys, "audioItems": audio_items},
            "song": self._empty_song(),
        }

    def _new_key(self) -> str:
        if self.seed is None:
            return str(uuid4())
        key = str(uuid5(NAMESPACE_URL, f"srszw-vvproj:{self.seed}:{self._key_index}"))
        self._key_index += 1
        return key

    def _empty_song(self) -> JsonObject:
        """Create the empty song section required by the 0.25.2 project schema."""

        track_key = self._new_key()
        return {
            "tpqn": 480,
            "tempos": [{"position": 0, "bpm": 120}],
            "timeSignatures": [{"measureNumber": 1, "beats": 4, "beatType": 4}],
            "tracks": {
                track_key: {
                    "name": "無名トラック",
                    "keyRangeAdjustment": 0,
                    "volumeRangeAdjustment": 0,
                    "notes": [],
                    "pitchEditData": [],
                    "volumeEditData": [],
                    "phonemeTimingEditData": {},
                    "solo": False,
                    "mute": False,
                    "gain": 1,
                    "pan": 0,
                }
            },
            "trackOrder": [track_key],
        }


def to_vvproj_query(query: AudioQuery) -> JsonObject:
    """Translate an Engine ``AudioQuery`` to the VVProj camelCase schema."""

    accent_phrases: list[JsonObject] = []
    for phrase in query["accent_phrases"]:
        moras: list[JsonObject] = []
        for mora in phrase["moras"]:
            vvproj_mora: JsonObject = {
                "text": mora["text"],
                "vowel": mora["vowel"],
                "vowelLength": mora["vowel_length"],
                "pitch": mora.get("pitch", 0.0),
            }
            consonant = mora["consonant"]
            if consonant is not None:
                vvproj_mora["consonant"] = consonant
                consonant_length = mora["consonant_length"]
                if consonant_length is None:
                    raise ProjectExportError("带辅音的 mora 缺少 consonant_length")
                vvproj_mora["consonantLength"] = consonant_length
            moras.append(vvproj_mora)

        vvproj_phrase: JsonObject = {
            "moras": moras,
            "accent": phrase["accent"],
            "isInterrogative": phrase["is_interrogative"],
        }
        pause_mora = phrase.get("pause_mora")
        if pause_mora is not None:
            vvproj_phrase["pauseMora"] = {
                "text": pause_mora["text"],
                "vowel": pause_mora["vowel"],
                "vowelLength": pause_mora["vowel_length"],
                "pitch": pause_mora["pitch"],
            }
        accent_phrases.append(vvproj_phrase)

    return {
        "accentPhrases": accent_phrases,
        "speedScale": query["speedScale"],
        "pitchScale": query["pitchScale"],
        "intonationScale": query["intonationScale"],
        "volumeScale": query["volumeScale"],
        "pauseLengthScale": query["pauseLengthScale"],
        "prePhonemeLength": query["prePhonemeLength"],
        "postPhonemeLength": query["postPhonemeLength"],
        "outputSamplingRate": query["outputSamplingRate"],
        "outputStereo": query["outputStereo"],
        "kana": query["kana"],
    }
