"""New subcommand CLI: direct TTS and query tooling.

The ``srszw`` entry point gains ``synthesize``, ``speakers`` and ``query``
subcommands in M2.  ``export-project`` follows in M3.  Flat legacy options
are routed to the compatibility handler in :mod:`srszw.main`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .api import ChineseSynthesizer, SynthesisOptions, build_audio_query
from .engine import EngineError, VoicevoxClient

DEFAULT_ENGINE_URL = "http://127.0.0.1:50021"
_KNOWN_SUBCOMMANDS = frozenset({"synthesize", "speakers", "query"})


def _add_common_engine_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--engine-url",
        default=DEFAULT_ENGINE_URL,
        help=f"VOICEVOX Engine 地址（默认 {DEFAULT_ENGINE_URL}）",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP 超时秒数")


def _add_synthesis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--speed-scale", type=float, default=1.0, help="语速")
    parser.add_argument("--pitch-scale", type=float, default=0.0, help="音高")
    parser.add_argument("--intonation-scale", type=float, default=1.0, help="抑扬")
    parser.add_argument("--volume-scale", type=float, default=1.0, help="音量")
    parser.add_argument(
        "--pre-phoneme-length", type=float, default=0.1, help="开始无音"
    )
    parser.add_argument(
        "--post-phoneme-length", type=float, default=0.1, help="终了无音"
    )
    parser.add_argument(
        "--pause-length-scale", type=float, default=1.0, help="停顿长度比例"
    )
    parser.add_argument(
        "--output-sampling-rate", type=int, default=24000, help="输出采样率"
    )
    parser.add_argument("--output-stereo", action="store_true", help="输出立体声 WAV")


def _options_from_args(args: argparse.Namespace) -> SynthesisOptions:
    return SynthesisOptions(
        speed_scale=args.speed_scale,
        pitch_scale=args.pitch_scale,
        intonation_scale=args.intonation_scale,
        volume_scale=args.volume_scale,
        pre_phoneme_length=args.pre_phoneme_length,
        post_phoneme_length=args.post_phoneme_length,
        pause_length_scale=args.pause_length_scale,
        output_sampling_rate=args.output_sampling_rate,
        output_stereo=args.output_stereo,
    )


def _new_client(args: argparse.Namespace) -> VoicevoxClient:
    return VoicevoxClient(args.engine_url, timeout=args.timeout)


def _read_text_input(args: argparse.Namespace) -> str:
    """Return text provided inline or loaded from a UTF-8 file."""

    if args.text is not None:
        return args.text
    return args.text_file.read_text(encoding="utf-8")


def _ensure_writable_output(path: Path, *, force: bool) -> None:
    """Refuse accidental overwrites unless the caller explicitly opts in."""

    if path.exists() and not force:
        raise FileExistsError(f"输出文件已存在: {path}；如需覆盖请使用 --force")


def _cmd_synthesize(args: argparse.Namespace) -> int:
    options = _options_from_args(args)
    text = _read_text_input(args)
    _ensure_writable_output(args.output, force=args.force)
    with _new_client(args) as client:
        synthesizer = ChineseSynthesizer(client, seed=args.seed)
        output_path = synthesizer.synthesize_to_file(
            text,
            args.speaker,
            args.output,
            options,
        )
    print(f"已生成: {output_path}")
    return 0


def _cmd_speakers(args: argparse.Namespace) -> int:
    with _new_client(args) as client:
        speakers = client.speakers()
    if args.json:
        print(json.dumps(speakers, ensure_ascii=False, indent=2))
        return 0
    for speaker in speakers:
        for style in speaker["styles"]:
            print(f"{style['id']}\t{style['name']}\t{speaker['name']}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    options = _options_from_args(args)
    query = build_audio_query(
        args.text,
        options,
        seed=args.seed,
    )
    json.dump(query, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Build the M2 subcommand parser (no legacy flat options)."""

    parser = argparse.ArgumentParser(prog="srszw", description="SRSZW 中文 TTS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    synthesize = subparsers.add_parser("synthesize", help="生成 WAV 音频")
    synthesize_input = synthesize.add_mutually_exclusive_group(required=True)
    synthesize_input.add_argument("--text", "-t", help="要合成的中文文本")
    synthesize_input.add_argument(
        "--text-file", type=Path, help="读取 UTF-8 文本文件并合成"
    )
    synthesize.add_argument(
        "--speaker", type=int, required=True, help="Engine style ID"
    )
    synthesize.add_argument(
        "--output", "-o", type=Path, required=True, help="输出 WAV 路径"
    )
    synthesize.add_argument("--force", action="store_true", help="允许覆盖已有输出文件")
    synthesize.add_argument("--seed", type=int, help="固定随机偏移，便于复现")
    _add_common_engine_arguments(synthesize)
    _add_synthesis_options(synthesize)
    synthesize.set_defaults(func=_cmd_synthesize)

    speakers = subparsers.add_parser("speakers", help="列出 Engine 角色")
    _add_common_engine_arguments(speakers)
    speakers.add_argument("--json", action="store_true", help="以 JSON 输出")
    speakers.set_defaults(func=_cmd_speakers)

    query = subparsers.add_parser("query", help="输出本地生成的 AudioQuery JSON")
    query.add_argument("--text", "-t", required=True, help="要转换的中文文本")
    query.add_argument("--seed", type=int, help="固定随机偏移，便于复现")
    _add_synthesis_options(query)
    query.set_defaults(func=_cmd_query)

    return parser


def run_subcommand(argv: Sequence[str] | None = None) -> int:
    """Parse and run a new-style subcommand, returning the process exit code."""

    parser = build_subcommand_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (EngineError, ValueError, OSError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
