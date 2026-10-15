"""`__main__.main()` is a thin wrapper - these tests monkeypatch
`orchestrator.run_platform` so they never touch real MCP/LLM, and only
check argument defaults + which summary branch gets printed, mirroring
test_orchestrator.py's "pure decision" testing style.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import __main__ as cli
from src.store import Store


def test_parse_args_defaults_dir_from_platform():
    args = cli._parse_args(["emdlz"])
    assert args.platform == "emdlz"
    assert args.dir is None


def test_parse_args_accepts_explicit_dir():
    args = cli._parse_args(["emdlz", "--dir", "/tmp/somewhere"])
    assert args.dir == Path("/tmp/somewhere")


async def _noop_run_platform(platform_dir, platform):
    return None


def test_main_defaults_platform_dir_to_handbook_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    async def _record(platform_dir, platform):
        seen["platform_dir"] = platform_dir

    monkeypatch.setattr(cli.orchestrator, "run_platform", _record)

    code = cli.main(["emdlz"])

    assert code == 0
    assert seen["platform_dir"] == Path("handbook/dms-sa/emdlz")


def test_main_reports_questions_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.orchestrator, "run_platform", _noop_run_platform)
    Store(tmp_path).write_questions(["dms_contract_sign_info：需要人工拍板"])

    code = cli.main(["emdlz", "--dir", str(tmp_path)])

    assert code == 0


def test_main_reports_failure_from_run_platform(tmp_path, monkeypatch, capsys):
    async def _boom(platform_dir, platform):
        raise RuntimeError("MCP 未连接")

    monkeypatch.setattr(cli.orchestrator, "run_platform", _boom)

    code = cli.main(["emdlz", "--dir", str(tmp_path)])

    assert code == 1
    assert "MCP 未连接" in capsys.readouterr().err


def test_main_reports_done_when_phase_done(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.orchestrator, "run_platform", _noop_run_platform)
    store = Store(tmp_path)
    manifest = store.load_manifest()
    manifest["phase"] = "done"
    store.save_manifest(manifest)

    code = cli.main(["emdlz", "--dir", str(tmp_path)])

    assert code == 0
    assert "完成" in capsys.readouterr().out
