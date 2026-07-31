"""High-level TTS orchestration: local Mandarin conversion + Engine synthesis.

The offline converter produces VVProj-style camelCase accent phrases; the
Engine HTTP contract requires snake_case field names.  ``ChineseSynthesizer``
bridges the two so callers only ever see stable public options.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .engine import VoicevoxClient
from .models import (
    AccentPhrase,
    AudioQuery,
    Mora,
    PauseMora,
    Speakers,
    SynthesisOptions,
)

if TYPE_CHECKING:
    from .project import ProjectUtterance, VoicevoxVoice
from .srszw_core import Config
from .srszw_core.converter import SRSZWConverter

__all__ = [
    "ChineseSynthesizer",
    "SynthesisOptions",
    "build_audio_query",
    "to_engine_query",
]


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

    def export_project(
        self,
        utterances: Sequence[ProjectUtterance],
        output_path: str | Path,
        *,
        speaker: int | None = None,
        options: SynthesisOptions = DEFAULT_OPTIONS,
        app_version: str = "0.25.2",
    ) -> Path:
        """Export an editable VVProj using the same conversion as synthesis.

        ``speaker`` and ``options`` are global defaults. Individual
        :class:`~srszw.ProjectUtterance` objects may override either setting.
        Voice UUIDs are obtained from the connected Engine, ensuring each talk
        item identifies the real speaker behind its requested style ID.
        """

        from .project import VVProjExporter

        manifest = self._client.engine_manifest()
        engine_id = manifest.get("uuid")
        if not isinstance(engine_id, str) or not engine_id:
            raise ValueError("/engine_manifest 未返回有效的 Engine UUID")
        exporter = VVProjExporter(app_version=app_version, seed=self._seed)
        project = exporter.export(
            utterances,
            self._voices_by_style(self._client.speakers(), engine_id),
            default_speaker=speaker,
            default_options=options,
            build_query=lambda text, item_options: build_audio_query(
                text,
                item_options,
                config=self._config,
                seed=self._seed,
            ),
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(project, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _voices_by_style(
        speakers: Speakers, engine_id: str
    ) -> dict[int, VoicevoxVoice]:
        """Build a talk-style lookup from an Engine speaker catalog."""

        from .project import VoicevoxVoice

        voices: dict[int, VoicevoxVoice] = {}
        for speaker in speakers:
            for style in speaker["styles"]:
                if style["type"] != "talk":
                    continue
                voices[style["id"]] = VoicevoxVoice(
                    engine_id=engine_id,
                    speaker_id=speaker["speaker_uuid"],
                    style_id=style["id"],
                )
        return voices
