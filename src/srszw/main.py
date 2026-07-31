"""Command-line entry point.

The console script ``srszw`` dispatches to the new subcommands when the first
positional token matches one of them; otherwise it runs the legacy flat
VVProj-export command for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .cli import _KNOWN_SUBCOMMANDS, run_subcommand
from .srszw_core import Config, ConversionError, SRSZWConverter
from .srszw_core.utils import generate_and_save


def build_parser() -> argparse.ArgumentParser:
    """Build the transitional flat command-line parser."""

    parser = argparse.ArgumentParser(description="将中文转换为 VOICEVOX 工程文件")
    parser.add_argument("--config", "-c", default="config.json", help="配置文件路径")
    parser.add_argument("--output", "-o", type=Path, help="输出文件路径")
    parser.add_argument("--text", "-t", help="直接输入文本进行转换")
    parser.add_argument(
        "--charactor",
        "-ch",
        default="shikokumetan",
        help="旧工程使用的角色别名",
    )
    parser.add_argument("--style", "-s", help="旧工程使用的声线别名")
    parser.add_argument(
        "--seed",
        type=int,
        help="固定随机偏移，令同一输入可复现",
    )
    return parser


def _run_legacy(args: argparse.Namespace) -> int:
    config = Config.from_file(args.config)
    if args.output is not None:
        config.output = args.output

    if args.text is not None:
        output_path = generate_and_save(
            text=args.text,
            output_path=config.output,
            charactor=args.charactor,
            style=args.style,
            config=config,
            seed=args.seed,
        )
        print(f"生成完成，已输出至: {output_path}")
        return 0

    converter = SRSZWConverter(config, seed=args.seed)
    project_path = config.file
    with project_path.open(encoding="utf-8") as file:
        project_data = json.load(file)
    if not isinstance(project_data, dict):
        raise ConversionError(f"项目文件必须是 JSON 对象: {project_path}")

    vvproj_data = converter.convert(project_data)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    with config.output.open("w", encoding="utf-8") as file:
        json.dump(vvproj_data, file, ensure_ascii=False, indent=2)
    print(f"生成完成，已输出至: {config.output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch to the new subcommands or the legacy flat command."""

    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] in _KNOWN_SUBCOMMANDS:
        return run_subcommand(raw_argv)

    if raw_argv:
        print(
            "提示: 检测到旧版扁平参数。使用 `srszw <子命令> --help` 可查看新的 "
            "synthesize / speakers / query 用法。",
            file=sys.stderr,
        )

    args = build_parser().parse_args(raw_argv)
    try:
        return _run_legacy(args)
    except (ConversionError, FileNotFoundError, json.JSONDecodeError, OSError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
