"""CLI entry point: `python -m dms_survey <平台名> [--dir PATH]`.

Thin wrapper around `orchestrator.run_platform()` - no pipeline logic lives
here. Progress truth is `manifest.json`/`questions.md` on disk (see
orchestrator.py's module docstring), so this only parses args, runs one
pass, and prints what changed so a human doesn't have to go open the files
themselves after every invocation.

Prerequisites (CLAUDE.md 人工前置, unchanged by this wrapper):
- Browser already opened and logged into the target platform by hand.
- JSReverser-Strong-MCP / image-annotator reachable (see mcp_client.py's
  DMS_JSREVERSER_*/DMS_ANNOTATOR_* env vars if not at the default paths).
- An LLM key set for whichever DMS_LLM_PROVIDER is configured (see
  model_config.py).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import orchestrator
from .store import QUESTIONS, Store


def _parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m dms_survey",
        description="跑一轮 dms_survey 流水线：Discovery -> 业务 agent 扇出 -> Judge 合稿/一致性自检。",
    )
    parser.add_argument("platform", help="平台名，如 emdlz；决定产出文档 <平台名>采集需求.md 的文件名前缀")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="平台目录，默认 handbook/dms-sa/<platform>；目录不需要预先存在，manifest.json 缺失时会自动初始化",
    )
    return parser.parse_args(argv)


def main(argv: "list[str] | None" = None) -> int:
    args = _parse_args(argv)
    platform_dir = args.dir or Path("handbook/dms-sa") / args.platform

    try:
        asyncio.run(orchestrator.run_platform(platform_dir, args.platform))
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report and exit non-zero, don't traceback-dump
        print(f"运行失败：{exc!r}", file=sys.stderr)
        return 1

    manifest = Store(platform_dir).load_manifest()
    print(f"phase = {manifest.get('phase')}")

    questions_path = platform_dir / QUESTIONS
    if questions_path.exists():
        print(f"\n有待人工确认的问题，见 {questions_path}：\n")
        print(questions_path.read_text(encoding="utf-8"))
    elif manifest.get("phase") == "done":
        print(f"完成：{args.platform}采集需求.md / {args.platform}技术笔记.md 已写入 {platform_dir}")
    else:
        print("本轮未完成也未产生待确认问题——再跑一次 python -m dms_survey 继续推进。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
