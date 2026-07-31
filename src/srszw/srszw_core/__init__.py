"""
srszw_core - VOICEVOX中文跨语种自动生成核心模块

提供将中文文本转换为VOICEVOX项目文件的核心功能。
"""

from .config import Config
from .converter import SRSZWConverter
from .utils import generate_from_string

__version__ = "0.1.0"
__all__ = ["Config", "SRSZWConverter", "generate_from_string"]
