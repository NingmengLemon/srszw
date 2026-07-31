"""
工具函数模块
包含便捷的工具函数和字符串输入接口
"""

import json
from typing import Any, Dict, List, Optional

from .config import Config
from .converter import SRSZWConverter


def generate_from_string(
    text: str,
    charactor: str = "shikokumetan",
    style: Optional[str] = None,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """
    从字符串生成VOICEVOX项目数据

    Args:
        text: 要转换的中文文本
        charactor: 角色名称，默认为"shikokumetan"
        style: 声线风格，默认为None（使用默认声线）
        config: 配置对象，默认为None（使用默认配置）

    Returns:
        VOICEVOX项目数据的字典表示
    """
    converter = SRSZWConverter(config)

    # 创建项目数据结构
    project_data = {
        "script_version": "0.1",
        "app_version": "0.23.0",
        "talk": [
            {
                "charactor": charactor,
                "style": style,
                "speedScale": 1,
                "pitchScale": 0,
                "intonationScale": 1,
                "volumeScale": 1,
                "prePhonemeLength": 0.1,
                "postPhonemeLength": 0.1,
                "pauseLengthScale": 1,
                "text": {"pinyin": None, "zi": text},
            }
        ],
    }

    return converter.convert(project_data)


def generate_from_strings(
    texts: List[str],
    charactor: str = "shikokumetan",
    style: Optional[str] = None,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """
    从多个字符串生成VOICEVOX项目数据

    Args:
        texts: 要转换的中文文本列表
        charactor: 角色名称，默认为"shikokumetan"
        style: 声线风格，默认为None（使用默认声线）
        config: 配置对象，默认为None（使用默认配置）

    Returns:
        VOICEVOX项目数据的字典表示
    """
    converter = SRSZWConverter(config)

    # 创建项目数据结构
    project_data = {"script_version": "0.1", "app_version": "0.23.0", "talk": []}

    for text in texts:
        project_data["talk"].append(
            {
                "charactor": charactor,
                "style": style,
                "speedScale": 1,
                "pitchScale": 0,
                "intonationScale": 1,
                "volumeScale": 1,
                "prePhonemeLength": 0.1,
                "postPhonemeLength": 0.1,
                "pauseLengthScale": 1,
                "text": {"pinyin": None, "zi": text},
            }
        )

    return converter.convert(project_data)


def save_vvproj(vvproj_data: Dict[str, Any], output_path: str) -> None:
    """
    保存VOICEVOX项目数据到文件

    Args:
        vvproj_data: VOICEVOX项目数据
        output_path: 输出文件路径
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(vvproj_data, f, ensure_ascii=False, indent=2)


def generate_and_save(
    text: str,
    output_path: str,
    charactor: str = "shikokumetan",
    style: Optional[str] = None,
    config: Optional[Config] = None,
) -> None:
    """
    从字符串生成并保存VOICEVOX项目文件

    Args:
        text: 要转换的中文文本
        output_path: 输出文件路径
        charactor: 角色名称，默认为"shikokumetan"
        style: 声线风格，默认为None（使用默认声线）
        config: 配置对象，默认为None（使用默认配置）
    """
    vvproj_data = generate_from_string(text, charactor, style, config)
    save_vvproj(vvproj_data, output_path)


def load_project_file(project_path: str) -> Dict[str, Any]:
    """
    加载项目文件

    Args:
        project_path: 项目文件路径

    Returns:
        项目数据字典
    """
    with open(project_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
            return data
        raise ValueError("项目文件格式不正确")


def convert_project_file(
    input_path: str, output_path: str, config: Optional[Config] = None
) -> None:
    """
    转换项目文件

    Args:
        input_path: 输入项目文件路径
        output_path: 输出VOICEVOX项目文件路径
        config: 配置对象，默认为None（使用默认配置）
    """
    converter = SRSZWConverter(config)
    project_data = load_project_file(input_path)
    vvproj_data = converter.convert(project_data)
    save_vvproj(vvproj_data, output_path)
