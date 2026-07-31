"""
配置管理模块
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Config:
    """配置类，用于管理srszw的配置参数"""

    # 文件路径配置
    file: str = "examples/example1.hooay-srszw.json"
    output: str = "output/output.vvproj"
    loaded_charactor_lists: List[str] = field(
        default_factory=lambda: ["data/charactors/vvx.json"]
    )

    # 数据文件路径
    yunMuSpliting: str = "data/yunMuSpliting/spliting.json"
    zhengTiRenDu: str = "data/zhengTiRenDu/zhenTiRenDu.json"
    shengDiao: str = "data/shengDiao/puTongHuaShengDiao.json"
    shengYun: str = "data/shengYunConvInfo/zh_in_jp1.json"
    kanaData: str = "data/kana.json"

    # 处理参数
    noYW: bool = False
    pitchRange: List[float] = field(default_factory=lambda: [5.5, 6.0])
    pitchRandom: float = 0.02
    lengthRandom: float = 0.001

    # 加载的数据
    _yunMuSplit_data: Optional[Dict] = None
    _shengDiao_data: Optional[Dict] = None
    _zhengTiRenDu_data: Optional[Dict] = None
    _shengYun_data: Optional[Dict] = None
    _kana_data: Optional[Dict] = None
    _charactors_data: Optional[List[Dict]] = None

    @classmethod
    def from_file(cls, config_path: str = "config.json") -> "Config":
        """从配置文件创建配置实例"""
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            return cls(**config_data)
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "file": self.file,
            "output": self.output,
            "loaded_charactor_lists": self.loaded_charactor_lists,
            "yunMuSpliting": self.yunMuSpliting,
            "zhengTiRenDu": self.zhengTiRenDu,
            "shengDiao": self.shengDiao,
            "shengYun": self.shengYun,
            "noYW": self.noYW,
            "pitchRange": self.pitchRange,
            "pitchRandom": self.pitchRandom,
            "lengthRandom": self.lengthRandom,
        }

    def save(self, config_path: str = "config.json"):
        """保存配置到文件"""
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def load_data_files(self):
        """加载所有数据文件"""
        self._yunMuSplit_data = self._load_json(self.yunMuSpliting)
        self._shengDiao_data = self._load_json(self.shengDiao)
        self._zhengTiRenDu_data = self._load_json(self.zhengTiRenDu)
        self._shengYun_data = self._load_json(self.shengYun)
        self._kana_data = self._load_json(self.kanaData)

        # 加载角色数据
        self._charactors_data = []
        for charactor_file in self.loaded_charactor_lists:
            self._charactors_data.append(self._load_json(charactor_file))

    def _load_json(self, file_path: str) -> Dict:
        """加载JSON文件"""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise FileNotFoundError(f"文件不存在: {file_path}")

    @property
    def yunMuSplit(self) -> Dict:
        """获取韵母拆分数据"""
        if self._yunMuSplit_data is None:
            self.load_data_files()
        return self._yunMuSplit_data

    @property
    def shengDiao_data(self) -> Dict:
        """获取声调数据"""
        if self._shengDiao_data is None:
            self.load_data_files()
        return self._shengDiao_data

    @property
    def zhengTiRenDu_data(self) -> Dict:
        """获取整体认读数据"""
        if self._zhengTiRenDu_data is None:
            self.load_data_files()
        return self._zhengTiRenDu_data

    @property
    def shengYun_data(self) -> Dict:
        """获取声韵数据"""
        if self._shengYun_data is None:
            self.load_data_files()
        return self._shengYun_data

    @property
    def kana(self) -> Dict:
        """获取假名数据"""
        if self._kana_data is None:
            self.load_data_files()
        return self._kana_data

    @property
    def charactors(self) -> List[Dict]:
        """获取角色数据"""
        if self._charactors_data is None:
            self.load_data_files()
        return self._charactors_data


# 默认配置实例
default_config = Config()
