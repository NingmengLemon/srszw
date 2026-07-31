"""Legacy-compatible configuration and packaged conversion-resource loading.

The public conversion defaults use clearly named JSON assets bundled with the
package. Historical configuration-field spellings remain only to preserve the
legacy VVProj-export compatibility path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar, Self

JsonMapping = dict[str, Any]


@dataclass
class Config:
    """Configure the offline Chinese-to-VOICEVOX conversion process.

    Conversion tables are bundled with :mod:`srszw` and are used by default.
    Path fields are only needed to replace an individual bundled table or load
    legacy character aliases from a local JSON file.
    """

    file: Path = Path("examples/example1.hooay-srszw.json")
    output: Path = Path("output/output.vvproj")
    loaded_charactor_lists: list[Path] = field(default_factory=list)

    # ``None`` means the data table packaged in ``srszw.data``.
    yunMuSpliting: Path | None = None
    zhengTiRenDu: Path | None = None
    shengDiao: Path | None = None
    shengYun: Path | None = None
    kanaData: Path | None = None

    noYW: bool = False
    pitchRange: tuple[float, float] = (5.5, 6.0)
    pitchRandom: float = 0.02
    lengthRandom: float = 0.001

    _yunMuSplit_data: JsonMapping | None = field(default=None, init=False, repr=False)
    _shengDiao_data: list[Any] | None = field(default=None, init=False, repr=False)
    _zhengTiRenDu_data: JsonMapping | None = field(default=None, init=False, repr=False)
    _shengYun_data: JsonMapping | None = field(default=None, init=False, repr=False)
    _kana_data: JsonMapping | None = field(default=None, init=False, repr=False)
    _charactors_data: list[JsonMapping] | None = field(
        default=None, init=False, repr=False
    )

    _RESOURCE_PACKAGE: ClassVar[str] = "srszw.data"
    _DEFAULT_YUNMU_SPLITTING: ClassVar[str] = "pinyin_final_splitting.json"
    _DEFAULT_ZHENGTI_RENDU: ClassVar[str] = "whole_syllable_pinyin.json"
    _DEFAULT_SHENGDIAO: ClassVar[str] = "mandarin_tone_contours.json"
    _DEFAULT_SHENGYUN: ClassVar[str] = "pinyin_to_voicevox_phonemes.json"
    _DEFAULT_KANA: ClassVar[str] = "phoneme_to_katakana.json"
    _DEFAULT_CHARACTORS: ClassVar[str] = "legacy/voicevox_speaker_aliases.json"
    _PATH_FIELDS: ClassVar[tuple[str, ...]] = (
        "file",
        "output",
        "yunMuSpliting",
        "zhengTiRenDu",
        "shengDiao",
        "shengYun",
        "kanaData",
    )

    def __post_init__(self) -> None:
        for name in self._PATH_FIELDS:
            value = getattr(self, name)
            if value is not None and not isinstance(value, Path):
                setattr(self, name, Path(value))
        self.loaded_charactor_lists = [
            path if isinstance(path, Path) else Path(path)
            for path in self.loaded_charactor_lists
        ]
        if len(self.pitchRange) != 2:
            raise ValueError("pitchRange 必须恰好包含两个值")
        self.pitchRange = (float(self.pitchRange[0]), float(self.pitchRange[1]))
        if self.pitchRange[0] > self.pitchRange[1]:
            raise ValueError("pitchRange 的最小值不能大于最大值")
        if self.pitchRandom < 0:
            raise ValueError("pitchRandom 不能为负数")
        if self.lengthRandom < 0:
            raise ValueError("lengthRandom 不能为负数")

    @classmethod
    def from_file(cls, config_path: str | Path = "config.json") -> Self:
        """Create a configuration from a legacy-compatible JSON file.

        Relative paths inside the file are resolved from the file's parent
        directory. If the file does not exist, a configuration using bundled
        data is returned, preserving the previous command-line behaviour.
        """

        path = Path(config_path)
        if not path.exists():
            return cls()

        with path.open(encoding="utf-8") as file:
            raw_config = json.load(file)
        if not isinstance(raw_config, dict):
            raise ValueError(f"配置文件必须是 JSON 对象: {path}")

        allowed_fields = {
            item.name for item in fields(cls) if not item.name.startswith("_")
        }
        unsupported_fields = set(raw_config).difference(allowed_fields)
        if unsupported_fields:
            names = ", ".join(sorted(unsupported_fields))
            raise ValueError(f"配置文件包含未知字段: {names}")

        values: dict[str, Any] = dict(raw_config)
        for name in set(cls._PATH_FIELDS).intersection(values):
            if values[name] is not None:
                values[name] = cls._resolve_config_path(values[name], path.parent)

        if "loaded_charactor_lists" in values:
            entries = values["loaded_charactor_lists"]
            if not isinstance(entries, list):
                raise ValueError("loaded_charactor_lists 必须是路径列表")
            values["loaded_charactor_lists"] = [
                cls._resolve_config_path(entry, path.parent) for entry in entries
            ]

        if "pitchRange" in values:
            pitch_range = values["pitchRange"]
            if not isinstance(pitch_range, list | tuple):
                raise ValueError("pitchRange 必须是数值列表")
            values["pitchRange"] = tuple(pitch_range)

        return cls(**values)

    @staticmethod
    def _resolve_config_path(value: object, base_directory: Path) -> Path:
        if not isinstance(value, str):
            raise ValueError("配置中的文件路径必须是字符串")
        candidate = Path(value)
        return candidate if candidate.is_absolute() else base_directory / candidate

    def to_dict(self) -> JsonMapping:
        """Return a JSON-serializable representation of this configuration."""

        result: JsonMapping = {
            "file": str(self.file),
            "output": str(self.output),
            "loaded_charactor_lists": [
                str(path) for path in self.loaded_charactor_lists
            ],
            "noYW": self.noYW,
            "pitchRange": list(self.pitchRange),
            "pitchRandom": self.pitchRandom,
            "lengthRandom": self.lengthRandom,
        }
        for name in (
            "yunMuSpliting",
            "zhengTiRenDu",
            "shengDiao",
            "shengYun",
            "kanaData",
        ):
            value = getattr(self, name)
            if value is not None:
                result[name] = str(value)
        return result

    def save(self, config_path: str | Path = "config.json") -> None:
        """Save the configuration as UTF-8 JSON."""

        with Path(config_path).open("w", encoding="utf-8") as file:
            json.dump(self.to_dict(), file, indent=2, ensure_ascii=False)

    def load_data_files(self) -> None:
        """Load conversion tables, using bundled resources unless overridden."""

        self._yunMuSplit_data = self._load_mapping(
            self.yunMuSpliting, self._DEFAULT_YUNMU_SPLITTING
        )
        self._shengDiao_data = self._load_list(self.shengDiao, self._DEFAULT_SHENGDIAO)
        self._zhengTiRenDu_data = self._load_mapping(
            self.zhengTiRenDu, self._DEFAULT_ZHENGTI_RENDU
        )
        self._shengYun_data = self._load_mapping(self.shengYun, self._DEFAULT_SHENGYUN)
        self._kana_data = self._load_mapping(self.kanaData, self._DEFAULT_KANA)

        if self.loaded_charactor_lists:
            self._charactors_data = [
                self._load_mapping(path, self._DEFAULT_CHARACTORS)
                for path in self.loaded_charactor_lists
            ]
        else:
            self._charactors_data = [self._load_mapping(None, self._DEFAULT_CHARACTORS)]

    @classmethod
    def _load_json(cls, path: Path | None, default_resource: str) -> object:
        if path is not None:
            try:
                with path.open(encoding="utf-8") as file:
                    return json.load(file)
            except FileNotFoundError as error:
                raise FileNotFoundError(f"文件不存在: {path}") from error

        try:
            content = (
                resources.files(cls._RESOURCE_PACKAGE)
                .joinpath(default_resource)
                .read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"未找到内置转换数据: {default_resource}"
            ) from error
        return json.loads(content)

    @classmethod
    def _load_mapping(cls, path: Path | None, default_resource: str) -> JsonMapping:
        data = cls._load_json(path, default_resource)
        if not isinstance(data, dict):
            raise ValueError(f"转换数据必须是 JSON 对象: {default_resource}")
        return data

    @classmethod
    def _load_list(cls, path: Path | None, default_resource: str) -> list[Any]:
        data = cls._load_json(path, default_resource)
        if not isinstance(data, list):
            raise ValueError(f"转换数据必须是 JSON 数组: {default_resource}")
        return data

    @property
    def yunMuSplit(self) -> JsonMapping:
        """The vowel-splitting conversion table."""

        if self._yunMuSplit_data is None:
            self.load_data_files()
        assert self._yunMuSplit_data is not None
        return self._yunMuSplit_data

    @property
    def shengDiao_data(self) -> list[Any]:
        """The Mandarin tone contour conversion table."""

        if self._shengDiao_data is None:
            self.load_data_files()
        assert self._shengDiao_data is not None
        return self._shengDiao_data

    @property
    def zhengTiRenDu_data(self) -> JsonMapping:
        """The whole-syllable recognition conversion table."""

        if self._zhengTiRenDu_data is None:
            self.load_data_files()
        assert self._zhengTiRenDu_data is not None
        return self._zhengTiRenDu_data

    @property
    def shengYun_data(self) -> JsonMapping:
        """The initial/final to mora conversion table."""

        if self._shengYun_data is None:
            self.load_data_files()
        assert self._shengYun_data is not None
        return self._shengYun_data

    @property
    def kana(self) -> JsonMapping:
        """The phoneme-to-katakana conversion table."""

        if self._kana_data is None:
            self.load_data_files()
        assert self._kana_data is not None
        return self._kana_data

    @property
    def charactors(self) -> list[JsonMapping]:
        """Legacy character alias tables used only for VVProj export."""

        if self._charactors_data is None:
            self.load_data_files()
        assert self._charactors_data is not None
        return self._charactors_data


# Compatibility export for callers that imported this name from earlier versions.
default_config = Config()
