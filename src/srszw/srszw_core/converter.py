"""Offline Chinese-to-VOICEVOX accent-phrase conversion."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

import pypinyin as pypy
import pypinyin.contrib.tone_convert as pypytc

from .config import Config

JsonObject = dict[str, Any]
Mora = JsonObject
AccentPhrase = JsonObject

_PUNCTUATION = frozenset(
    ",./<>?:;'\"[]{}!@#$%^&*()_+~`=-|\\，。《》？：；‘’【】！￥……（）——+｜\\·「」、"
)


class ConversionError(ValueError):
    """Raised when text cannot be represented with the bundled conversion data."""


class SRSZWConverter:
    """Convert Mandarin Chinese text into VOICEVOX-compatible accent phrases.

    The converter is offline: it loads tables packaged with SRSZW and never
    contacts a VOICEVOX Engine. Pass ``seed`` to make its optional timing and
    pitch variation reproducible.
    """

    def __init__(
        self, config: Config | None = None, *, seed: int | None = None
    ) -> None:
        self.config = config or Config()
        self.config.load_data_files()
        self._random = random.Random(seed)
        self._seed = seed

    def rand_len(self) -> float:
        """Return a configured random mora-duration offset."""

        return self._random.uniform(-self.config.lengthRandom, self.config.lengthRandom)

    def rand_pit(self) -> float:
        """Return a configured random pitch offset."""

        return self._random.uniform(-self.config.pitchRandom, self.config.pitchRandom)

    def get_sheng_yun(self, pinyin: str) -> list[str | None]:
        """Split a numbered Pinyin syllable into initial and three finals."""

        normalized_pinyin = pypytc.to_normal(pinyin)
        whole_syllable = self.config.zhengTiRenDu_data.get(normalized_pinyin)
        if whole_syllable is not None:
            return self._as_syllable(whole_syllable, pinyin)

        initial = pypytc.to_initials(pinyin, strict=self.config.noYW)
        processed_pinyin = (
            pinyin.replace("ju", "jv")
            .replace("qu", "qv")
            .replace("xu", "xv")
            .replace("yu", "yv")
        )
        final = pypytc.to_finals(processed_pinyin, strict=False)
        try:
            finals = self.config.yunMuSplit[final]
        except KeyError as error:
            raise ConversionError(
                f"不支持的拼音韵母: {pinyin!r}（韵母 {final!r}）"
            ) from error

        return [initial or None, *self._as_finals(finals, pinyin)]

    @staticmethod
    def _as_syllable(value: object, pinyin: str) -> list[str | None]:
        if not isinstance(value, list) or len(value) != 4:
            raise ConversionError(f"整体认读数据格式无效: {pinyin!r}")
        initial, *finals = value
        if initial is not None and not isinstance(initial, str):
            raise ConversionError(f"整体认读声母无效: {pinyin!r}")
        return [initial, *SRSZWConverter._as_finals(finals, pinyin)]

    @staticmethod
    def _as_finals(value: object, pinyin: str) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) != 3
            or not all(isinstance(item, str) for item in value)
        ):
            raise ConversionError(f"韵母拆分数据格式无效: {pinyin!r}")
        return value

    @staticmethod
    def first_vowel(convert_info: Sequence[object]) -> list[Any]:
        """Return the first vowel conversion entry for a final."""

        final_info = convert_info[1]
        if not isinstance(final_info, list) or not final_info:
            raise ConversionError("韵母转换数据为空")
        first_entry = final_info[0]
        entry = final_info[1] if isinstance(first_entry, dict) else first_entry
        if not isinstance(entry, list) or len(entry) < 4:
            raise ConversionError("韵母转换数据格式无效")
        return entry

    def convert_to_moras(self, convert_info: Sequence[object]) -> list[Mora]:
        """Convert an initial/final conversion entry into VOICEVOX moras."""

        if len(convert_info) != 2:
            raise ConversionError("声韵转换数据必须包含声母和韵母")
        initial_info, final_info = convert_info
        if not isinstance(final_info, list) or not final_info:
            raise ConversionError("韵母转换数据为空")

        result: list[Mora] = []
        if initial_info is not None:
            if not isinstance(initial_info, list):
                raise ConversionError("声母转换数据格式无效")
            for entry in initial_info:
                if not isinstance(entry, list) or len(entry) < 4:
                    raise ConversionError("声母转换数据格式无效")
                consonant, vowel, consonant_length, vowel_length = entry[:4]
                if not isinstance(consonant, str) or not isinstance(
                    consonant_length, int | float
                ):
                    raise ConversionError("声母转换数据格式无效")

                resolved_vowel = vowel
                resolved_vowel_length = vowel_length
                if resolved_vowel is None:
                    first_vowel = self.first_vowel(convert_info)
                    resolved_vowel = first_vowel[1]
                    resolved_vowel_length = (
                        vowel_length if vowel_length is not None else first_vowel[3]
                    )
                if not isinstance(resolved_vowel, str) or not isinstance(
                    resolved_vowel_length, int | float
                ):
                    raise ConversionError("声母元音转换数据格式无效")

                result.append(
                    {
                        "consonant": consonant,
                        "consonantLength": consonant_length + self.rand_len(),
                        "vowel": resolved_vowel,
                        "vowelLength": resolved_vowel_length + self.rand_len(),
                        "text": self._kana_for(consonant, resolved_vowel),
                    }
                )

        loop_times = 1
        entries = final_info
        if isinstance(final_info[0], dict):
            loop_times = final_info[0].get("loop")
            entries = final_info[1:]
        if not isinstance(loop_times, int) or loop_times < 1:
            raise ConversionError("韵母循环次数无效")

        for loop_index in range(loop_times):
            for entry_index, entry in enumerate(entries):
                if not isinstance(entry, list) or len(entry) < 4:
                    raise ConversionError("韵母转换数据格式无效")
                consonant, vowel, consonant_length, vowel_length = entry[:4]
                is_bridge = len(entry) > 4 and entry[4] == "Bridge"
                if (
                    loop_index == 0
                    and entry_index == 0
                    and initial_info
                    and isinstance(initial_info, list)
                    and isinstance(initial_info[-1], list)
                    and initial_info[-1][1] is None
                ):
                    continue
                if is_bridge and initial_info is None:
                    continue
                if not isinstance(vowel, str) or not isinstance(
                    vowel_length, int | float
                ):
                    raise ConversionError("韵母元音转换数据格式无效")

                mora: Mora = {
                    "vowel": vowel,
                    "vowelLength": vowel_length + self.rand_len(),
                    "text": self._kana_for(consonant, vowel),
                }
                if consonant is not None:
                    if not isinstance(consonant, str) or not isinstance(
                        consonant_length, int | float
                    ):
                        raise ConversionError("韵母声母转换数据格式无效")
                    mora["consonant"] = consonant
                    mora["consonantLength"] = consonant_length + self.rand_len()
                result.append(mora)

        if not result:
            raise ConversionError("拼音未生成任何音素")
        return result

    def _kana_for(self, consonant: object, vowel: str) -> str:
        key = f"{consonant or ''}{vowel}"
        try:
            kana = self.config.kana[key]
        except KeyError as error:
            raise ConversionError(f"缺少音素假名映射: {key!r}") from error
        if not isinstance(kana, str):
            raise ConversionError(f"音素假名映射无效: {key!r}")
        return kana

    def convert_to_accent_phrase_without_pitch(
        self, syllable: Sequence[str | None]
    ) -> AccentPhrase:
        """Create an accent phrase for one Pinyin syllable without pitch."""

        if len(syllable) != 4:
            raise ConversionError("拼音必须拆分为一个声母和三个韵母")
        initial, first, second, third = syllable
        try:
            initial_info = (
                self.config.shengYun_data["shengmu"][initial] if initial else None
            )
            final_infos = [
                self.config.shengYun_data["yunmu"][item]
                for item in (first, second, third)
            ]
        except KeyError as error:
            raise ConversionError(f"缺少声韵音素映射: {syllable!r}") from error

        return {
            "moras": self.convert_to_moras([initial_info, final_infos[0]])
            + self.convert_to_moras([None, final_infos[1]])
            + self.convert_to_moras([None, final_infos[2]]),
            "accent": 1,
            "isInterrogative": False,
        }

    def tone_to_pitch(self, tone: int, step: float) -> float:
        """Map a Mandarin tone and normalized mora position to VOICEVOX pitch."""

        if tone not in range(1, 6):
            raise ConversionError(f"拼音声调必须在 1 到 5 之间，得到: {tone}")
        if not 0 < step <= 1 + 1e-12:
            raise ConversionError(f"音高位置必须在 (0, 1] 中，得到: {step}")
        step = min(step, 1.0)

        contour = self.config.shengDiao_data[tone - 1]
        if (
            not isinstance(contour, list)
            or len(contour) != 3
            or not all(isinstance(value, int | float) for value in contour)
        ):
            raise ConversionError(f"声调数据格式无效: {tone}")

        if step < 0.5:
            pitch_step = contour[0] + (contour[1] - contour[0]) * step * 2 - 1
        else:
            pitch_step = contour[1] + (contour[2] - contour[1]) * (step - 0.5) * 2 - 1
        pitch_step /= 4
        return (
            (self.config.pitchRange[1] - self.config.pitchRange[0]) * pitch_step
            + self.config.pitchRange[0]
            + self.rand_pit()
        )

    def add_pause_mora(self, accent_phrase: AccentPhrase) -> AccentPhrase:
        """Attach a VOICEVOX pause mora to an accent phrase."""

        accent_phrase["pauseMora"] = {
            "text": "、",
            "vowel": "pau",
            "vowelLength": 0.3 + self.rand_len(),
            "pitch": 0,
        }
        return accent_phrase

    def add_pitch(self, moras: list[Mora], tone: int) -> list[Mora]:
        """Apply the Mandarin tone contour to a phrase's moras."""

        full_length = sum(float(mora["vowelLength"]) for mora in moras)
        if full_length <= 0:
            raise ConversionError("音素总时长必须大于零")

        elapsed_length = 0.0
        for mora in moras:
            elapsed_length += float(mora["vowelLength"])
            mora["pitch"] = self.tone_to_pitch(tone, elapsed_length / full_length)
            if tone == 5:
                mora["vowelLength"] = float(mora["vowelLength"]) * 0.6
        return moras

    @staticmethod
    def zi_to_pinyin(text: str) -> list[str]:
        """Convert Chinese text to numbered Pinyin tokens and punctuation."""

        if not text.strip():
            raise ConversionError("文本不能为空")
        return pypy.lazy_pinyin(
            text,
            style=pypy.Style.TONE3,
            strict=False,
            neutral_tone_with_five=True,
            tone_sandhi=True,
        )

    def accent_phrases_from_pinyin(self, tokens: Sequence[str]) -> list[AccentPhrase]:
        """Convert numbered Pinyin and punctuation tokens to accent phrases."""

        accent_phrases: list[AccentPhrase] = []
        for token in tokens:
            if not token or token.isspace():
                continue
            if all(character in _PUNCTUATION for character in token):
                if accent_phrases:
                    self.add_pause_mora(accent_phrases[-1])
                continue
            if not token[-1:].isdigit():
                raise ConversionError(
                    f"不支持的文本片段: {token!r}；请使用带声调数字的拼音或移除该片段"
                )
            tone = int(token[-1])
            phrase = self.convert_to_accent_phrase_without_pitch(
                self.get_sheng_yun(token)
            )
            phrase["moras"] = self.add_pitch(phrase["moras"], tone)
            accent_phrases.append(phrase)
        if not accent_phrases:
            raise ConversionError("文本未包含可转换的中文或拼音音节")
        return accent_phrases

    def accent_phrases(self, text: str) -> list[AccentPhrase]:
        """Convert Chinese text into VOICEVOX-compatible accent phrases."""

        return self.accent_phrases_from_pinyin(self.zi_to_pinyin(text))

    def generate_key(self) -> str:
        """Generate a UUID suitable for legacy VVProj object keys.

        A seeded converter derives keys from the same local random generator,
        making complete legacy project documents reproducible in tests and
        automation. Unseeded conversion continues to use random UUID4 values.
        """

        if self._seed is None:
            from uuid import uuid4

            return str(uuid4())
        first = self._random.randint(0, 0xFFFF)
        second = self._random.randint(0, 0xFFFF)
        third = self._random.randint(0, 0xFFFF)
        fourth = self._random.randint(0, 0xFFFFFFFFFFFF)
        return f"600a4233-{first:0>4x}-{second:0>4x}-{third:0>4x}-{fourth:0>12x}"

    def convert(self, project_data: JsonObject) -> JsonObject:
        """Convert a legacy SRSZW project document into a VOICEVOX VVProj."""

        app_version = project_data.get("app_version")
        talks = project_data.get("talk")
        if not isinstance(app_version, str) or not isinstance(talks, list):
            raise ConversionError("工程必须包含字符串 app_version 和列表 talk")

        vvproj: JsonObject = {
            "appVersion": app_version,
            "song": self._empty_song(),
            "talk": {"audioKeys": [], "audioItems": {}},
        }
        audio_keys = vvproj["talk"]["audioKeys"]
        audio_items = vvproj["talk"]["audioItems"]
        assert isinstance(audio_keys, list)
        assert isinstance(audio_items, dict)

        for talk in talks:
            if not isinstance(talk, dict):
                raise ConversionError("talk 中的每项必须是对象")
            text_data = talk.get("text")
            if not isinstance(text_data, dict):
                raise ConversionError("talk 项必须包含 text 对象")
            text = text_data.get("zi")
            pinyin = text_data.get("pinyin")
            if not isinstance(text, str):
                raise ConversionError("text.zi 必须是字符串")
            if pinyin is not None and not isinstance(pinyin, str):
                raise ConversionError("text.pinyin 必须为字符串或 null")

            key = self.generate_key()
            audio_keys.append(key)
            audio_items[key] = {
                "text": text,
                "voice": self._legacy_voice(talk),
                "query": {
                    "accentPhrases": self.accent_phrases_from_pinyin(
                        pinyin.split() if pinyin else self.zi_to_pinyin(text)
                    ),
                    "speedScale": self._talk_number(talk, "speedScale", 1.0),
                    "pitchScale": self._talk_number(talk, "pitchScale", 0.0),
                    "intonationScale": self._talk_number(talk, "intonationScale", 1.0),
                    "volumeScale": self._talk_number(talk, "volumeScale", 1.0),
                    "prePhonemeLength": self._talk_number(
                        talk, "prePhonemeLength", 0.1
                    ),
                    "postPhonemeLength": self._talk_number(
                        talk, "postPhonemeLength", 0.1
                    ),
                    "pauseLengthScale": self._talk_number(
                        talk, "pauseLengthScale", 1.0
                    ),
                    "outputSamplingRate": 48000,
                    "outputStereo": False,
                    "kana": "",
                },
            }

        return vvproj

    @staticmethod
    def _talk_number(talk: JsonObject, name: str, default: float) -> float:
        value = talk.get(name, default)
        if not isinstance(value, int | float):
            raise ConversionError(f"talk.{name} 必须是数值")
        return float(value)

    @staticmethod
    def _empty_song() -> JsonObject:
        track_key = "725cfeb6-b161-49d3-b301-1042bceea90b"
        return {
            "tpqn": 480,
            "tempos": [{"position": 0, "bpm": 120}],
            "timeSignatures": [{"measureNumber": 1, "beats": 4, "beatType": 4}],
            "tracks": {
                track_key: {
                    "name": "無名トラック",
                    "singer": {
                        "engineId": "074fc39e-678b-4c13-8916-ffca8d505d1d",
                        "styleId": 3002,
                    },
                    "keyRangeAdjustment": -4,
                    "volumeRangeAdjustment": 0,
                    "notes": [],
                    "pitchEditData": [],
                    "solo": False,
                    "mute": False,
                    "gain": 1,
                    "pan": 0,
                }
            },
            "trackOrder": [track_key],
        }

    def _legacy_voice(self, talk: JsonObject) -> JsonObject:
        character = talk.get("charactor")
        style = talk.get("style")
        if not isinstance(character, str):
            raise ConversionError("talk.charactor 必须是字符串")
        if style is not None and not isinstance(style, str):
            raise ConversionError("talk.style 必须为字符串或 null")

        for character_data in self.config.charactors:
            character_info = character_data.get(character)
            if not isinstance(character_info, dict):
                continue
            speaker_id = character_info.get("id")
            styles = character_info.get("styles")
            default_style = character_info.get("normalstyle")
            engine_id = character_data.get("engine_id")
            if not isinstance(speaker_id, str) or not isinstance(engine_id, str):
                raise ConversionError(f"角色数据格式无效: {character!r}")
            if style is None:
                style_id = default_style
            elif isinstance(styles, dict):
                style_id = styles.get(style)
            else:
                style_id = None
            if not isinstance(style_id, int):
                raise ConversionError(f"未找到角色声线: {character!r}, {style!r}")
            return {
                "engineId": engine_id,
                "speakerId": speaker_id,
                "styleId": style_id,
                "presetKey": self.generate_key(),
            }

        raise ConversionError(f"未找到角色: {character!r}")
