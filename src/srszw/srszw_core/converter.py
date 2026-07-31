"""
核心转换器模块
包含将中文文本转换为VOICEVOX项目文件的核心逻辑
"""

import random as rd
from typing import Any, Dict, List, Optional

import pypinyin as pypy
import pypinyin.contrib.tone_convert as pypytc

from .config import Config


class SRSZWConverter:
    """VOICEVOX中文跨语种转换器"""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.config.load_data_files()

    def rand_len(self) -> float:
        """生成随机长度偏移"""
        return (self.config.lengthRandom * 2) * rd.random() - self.config.lengthRandom

    def rand_pit(self) -> float:
        """生成随机音高偏移"""
        return (self.config.pitchRandom * 2) * rd.random() - self.config.pitchRandom

    def get_sheng_yun(self, pinyin: str) -> List[Optional[str]]:
        """获取声韵"""
        result = [None]
        try:
            # 尝试整体认读
            normalized_pinyin = pypytc.to_normal(pypytc.to_normal(pinyin))
            result = self.config.zhengTiRenDu_data[normalized_pinyin]
            return result
        except KeyError:
            # 非整体认读音节，进行声韵拆分
            pass

        # 获取声母
        result[0] = pypytc.to_initials(pinyin, strict=self.config.noYW)

        # 处理特殊韵母转换
        processed_pinyin = (
            pinyin.replace("ju", "jv")
            .replace("qu", "qv")
            .replace("xu", "xv")
            .replace("yu", "yv")
        )

        # 获取韵母并进行拆分
        finals = pypytc.to_finals(processed_pinyin, strict=False)
        result += self.config.yunMuSplit[finals]

        return result

    @staticmethod
    def first_vowel(convert_info: List) -> Any:
        """获取第一个元音"""
        if isinstance(convert_info[1][0], dict):
            return convert_info[1][1]
        else:
            return convert_info[1][0]

    def convert_to_moras(self, convert_info: List) -> List[Dict[str, Any]]:
        """将声韵转换为日语音节"""
        result = []

        # 处理声母部分
        if convert_info[0]:
            for i in range(len(convert_info[0])):
                result.append({})
                result[-1]["consonant"] = convert_info[0][i][0]
                result[-1]["consonantLength"] = convert_info[0][i][2] + self.rand_len()

                if convert_info[0][i][1]:
                    result[-1]["vowel"] = convert_info[0][i][1]
                    result[-1]["vowelLength"] = convert_info[0][i][3] + self.rand_len()
                else:
                    result[-1]["vowel"] = self.first_vowel(convert_info)[1]
                    result[-1]["vowelLength"] = (
                        convert_info[0][i][3] + self.rand_len()
                        if convert_info[0][i][3]
                        else self.first_vowel(convert_info)[3] + self.rand_len()
                    )

                result[-1]["text"] = self.config.kana[
                    result[-1]["consonant"] + result[-1]["vowel"]
                ]

        # 处理韵母部分
        if isinstance(convert_info[1][0], dict):
            loop_times = convert_info[1][0]["loop"]
        else:
            loop_times = 1
            convert_info[1] = [[]] + convert_info[1]

        for i in range(loop_times):
            for j in range(1, len(convert_info[1])):
                # 跳过某些特殊情况
                if i == 0 and j == 1 and convert_info[0] and not convert_info[0][-1][1]:
                    continue
                if convert_info[1][j][-1] == "Bridge" and not convert_info[0]:
                    continue

                result.append({})
                if convert_info[1][j][0]:
                    result[-1]["consonant"] = convert_info[1][j][0]
                    result[-1]["consonantLength"] = (
                        convert_info[1][j][2] + self.rand_len()
                    )

                result[-1]["vowel"] = convert_info[1][j][1]
                result[-1]["vowelLength"] = convert_info[1][j][3] + self.rand_len()

                try:
                    result[-1]["text"] = self.config.kana[
                        result[-1]["consonant"] + result[-1]["vowel"]
                    ]
                except KeyError:
                    result[-1]["text"] = self.config.kana[result[-1]["vowel"]]

        return result

    def convert_to_accent_phrase_without_pitch(self, sy: List) -> Dict[str, Any]:
        """转换为无音高的重音短语"""
        convert_info = [
            self.config.shengYun_data["shengmu"][sy[0]] if sy[0] else None,
            self.config.shengYun_data["yunmu"][sy[1]],
            self.config.shengYun_data["yunmu"][sy[2]],
            self.config.shengYun_data["yunmu"][sy[3]],
        ]

        result = {}
        result["moras"] = (
            self.convert_to_moras(convert_info[0:2])
            + self.convert_to_moras([None, convert_info[2]])
            + self.convert_to_moras([None, convert_info[3]])
        )
        result["accent"] = 1
        result["isInterrogative"] = False

        return result

    def tone_to_pitch(self, tone: int, step: float) -> float:
        """声调转成音高"""
        tone -= 1
        if step < 0.5:
            pitch_step = (
                self.config.shengDiao_data[tone][0]
                + (
                    self.config.shengDiao_data[tone][1]
                    - self.config.shengDiao_data[tone][0]
                )
                * step
                * 2
                - 1
            ) / 4
        else:
            pitch_step = (
                self.config.shengDiao_data[tone][1]
                + (
                    self.config.shengDiao_data[tone][2]
                    - self.config.shengDiao_data[tone][1]
                )
                * (step - 0.5)
                * 2
                - 1
            ) / 4

        pitch = (
            ((self.config.pitchRange[1] - self.config.pitchRange[0]) * pitch_step)
            + self.config.pitchRange[0]
        ) + self.rand_pit()

        return pitch

    def add_pause_mora(self, accent_phrase: Dict[str, Any]) -> Dict[str, Any]:
        """添加停顿"""
        accent_phrase["pauseMora"] = {
            "text": "、",
            "vowel": "pau",
            "vowelLength": 0.3 + self.rand_len(),
            "pitch": 0,
        }
        return accent_phrase

    def add_pitch(self, moras: List[Dict[str, Any]], tone: int) -> List[Dict[str, Any]]:
        """添加音高"""
        result = moras
        ready_len = 0
        full_len = 0

        for mora in moras:
            full_len += mora["vowelLength"]

        for i in range(len(moras)):
            ready_len += moras[i]["vowelLength"]
            step = ready_len / full_len
            result[i]["pitch"] = self.tone_to_pitch(tone, step)

            if tone == 5:
                result[i]["vowelLength"] *= 0.6

        return result

    @staticmethod
    def zi_to_pinyin(zi: str) -> List[str]:
        """汉字转拼音"""
        return (
            " ".join(
                pypy.lazy_pinyin(
                    zi,
                    style=pypy.Style.TONE3,
                    strict=0,
                    neutral_tone_with_five=True,
                    tone_sandhi=True,
                )
            )
        ).split(" ")

    @staticmethod
    def generate_key() -> str:
        """生成唯一键"""
        return "600a4233-{:0>4x}-{:0>4x}-{:0>4x}-{:0>12x}".format(
            rd.randint(0, 0xFFFF),
            rd.randint(0, 0xFFFF),
            rd.randint(0, 0xFFFF),
            rd.randint(0, 0xFFFFFFFFFFFF),
        )

    def convert(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """转换项目数据为VOICEVOX项目格式"""
        vvproj = {}
        vvproj["appVersion"] = project_data["app_version"]

        # 基础歌曲配置
        vvproj["song"] = {
            "tpqn": 480,
            "tempos": [{"position": 0, "bpm": 120}],
            "timeSignatures": [{"measureNumber": 1, "beats": 4, "beatType": 4}],
            "tracks": {
                "725cfeb6-b161-49d3-b301-1042bceea90b": {
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
            "trackOrder": ["725cfeb6-b161-49d3-b301-1042bceea90b"],
        }

        vvproj["talk"] = {}
        talk = project_data["talk"]
        vvproj["talk"]["audioKeys"] = []
        vvproj["talk"]["audioItems"] = {}

        for i in talk:
            key = self.generate_key()
            vvproj["talk"]["audioKeys"].append(key)
            vvproj["talk"]["audioItems"][key] = {}
            vvproj["talk"]["audioItems"][key]["text"] = str(i["text"]["zi"])

            # 查找角色信息
            charactor_id = None
            style_id = None
            engine_id = None

            for charactor_data in self.config.charactors:
                try:
                    charactor_id = charactor_data[i["charactor"]]["id"]
                    style_id = (
                        charactor_data[i["charactor"]]["styles"][i["style"]]
                        if i["style"]
                        else charactor_data[i["charactor"]]["normalstyle"]
                    )
                    engine_id = charactor_data["engine_id"]
                    break
                except KeyError:
                    continue

            if charactor_id is None:
                raise ValueError(f"未找到角色: {i['charactor']}")

            vvproj["talk"]["audioItems"][key]["voice"] = {
                "engineId": engine_id,
                "speakerId": charactor_id,
                "styleId": style_id,
                "presetKey": self.generate_key(),
            }

            vvproj["talk"]["audioItems"][key]["query"] = {
                "accentPhrases": [],
                "speedScale": i["speedScale"],
                "pitchScale": i["pitchScale"],
                "intonationScale": i["intonationScale"],
                "volumeScale": i["volumeScale"],
                "prePhonemeLength": i["prePhonemeLength"],
                "postPhonemeLength": i["postPhonemeLength"],
                "pauseLengthScale": i["pauseLengthScale"],
                "outputSamplingRate": 48000,
                "outputStereo": False,
                "kana": "",
            }

            accent_phrases = []

            # 获取拼音
            if i["text"]["pinyin"]:
                pinyin = i["text"]["pinyin"].split(" ")
            else:
                pinyin = self.zi_to_pinyin(i["text"]["zi"])

            # 处理每个拼音
            for j in range(len(pinyin)):
                if (
                    pinyin[j] in ",./<>?:;'\"[]{}!@#$%^&*()_+~`=-|\\，。《》？：；‘’"
                    "【】！￥……（）——+｜\\·「」、"
                ):
                    if accent_phrases:
                        self.add_pause_mora(accent_phrases[-1])
                else:
                    sheng_yun = self.get_sheng_yun(pinyin[j])
                    accent_p = self.convert_to_accent_phrase_without_pitch(sheng_yun)
                    accent_p["moras"] = self.add_pitch(
                        accent_p["moras"], int(pinyin[j][-1])
                    )
                    accent_phrases.append(accent_p)

            vvproj["talk"]["audioItems"][key]["query"]["accentPhrases"] = accent_phrases

        return vvproj
