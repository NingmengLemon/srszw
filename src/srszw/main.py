#!/usr/bin/env python3
"""
srszw - VOICEVOX中文跨语种自动生成脚本
重构后的主程序文件，使用新的srszw_core模块
"""

import argparse
import json

from .srszw_core import Config, SRSZWConverter
from .srszw_core.utils import generate_and_save


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="VOICEVOX中文跨语种自动生成脚本")
    parser.add_argument("--config", "-c", default="config.json", help="配置文件路径")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--text", "-t", help="直接输入文本进行转换")
    parser.add_argument("--charactor", "-ch", default="shikokumetan", help="角色名称")
    parser.add_argument("--style", "-s", help="声线风格")

    args = parser.parse_args()

    # 加载配置
    config = Config.from_file(args.config)

    if args.output:
        config.output = args.output

    if args.text:
        # 直接转换文本
        print(f"正在转换文本: {args.text}")
        generate_and_save(
            text=args.text,
            output_path=config.output,
            charactor=args.charactor,
            style=args.style,
            config=config,
        )
        print(f"生成完成，已输出至: {config.output}")
    else:
        # 从项目文件转换
        converter = SRSZWConverter(config)

        # 加载项目文件
        try:
            with open(config.file, "r", encoding="utf-8") as f:
                project_data = json.load(f)
        except FileNotFoundError:
            print(f"错误: 项目文件不存在: {config.file}")
            return 1
        except json.JSONDecodeError as e:
            print(f"错误: JSON格式错误: {e}")
            return 1

        # 转换项目
        print(f"正在转换项目: {config.file}")
        vvproj_data = converter.convert(project_data)

        # 保存结果
        try:
            with open(config.output, "w", encoding="utf-8") as f:
                json.dump(vvproj_data, f, ensure_ascii=False, indent=2)
            print(f"生成完成，已输出至: {config.output}")
        except IOError as e:
            print(f"错误: 无法写入输出文件: {e}")
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
