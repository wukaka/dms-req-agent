"""Disk I/O for the platform handbook directory.

manifest.json is the single source of progress truth, so every write goes
through a temp file + atomic replace, and unknown keys are always preserved:
the phase-2..5 pipeline and the previous architecture both wrote fields we do
not model here, and losing them would be silent data loss.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from .models import TABLES, DiscoveryBlock, EntryInfo, Existence

MANIFEST = "manifest.json"
EVIDENCE_INDEX = "evidence_index.json"
BLACKBOARD = "blackboard.md"
QUESTIONS = "questions.md"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, platform_dir: Path | str) -> None:
        self.dir = Path(platform_dir)

    # ---------- manifest ----------

    def load_manifest(self) -> dict[str, Any]:
        path = self.dir / MANIFEST
        if not path.exists():
            return {"system": self.dir.name, "phase": "probing", "tables": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            self.dir / MANIFEST,
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )

    def ensure_tables(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Guarantee one entry per contract table, in contract order."""
        by_name = {t.get("table"): t for t in manifest.get("tables", [])}
        ordered: list[dict[str, Any]] = []
        for name in TABLES:
            ordered.append(by_name.pop(name, None) or {"table": name, "status": "todo"})
        # Anything unrecognised is kept rather than dropped.
        ordered.extend(by_name.values())
        manifest["tables"] = ordered
        return manifest

    def set_discovery(self, manifest: dict[str, Any], block: DiscoveryBlock) -> dict[str, Any]:
        manifest["discovery"] = block.model_dump(mode="json")
        return manifest

    def set_verdict(
        self,
        manifest: dict[str, Any],
        table: str,
        existence: Existence,
        entry: Optional[EntryInfo] = None,
        notes: Optional[str] = None,
        deferred_questions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Merge a verdict into a table entry without disturbing other keys.

        `deferred_questions` replaces rather than appends: it reflects this
        run's own understanding, and a re-launched table (after a crash, or a
        human editing the manifest) starts that understanding over rather than
        piling old questions onto new ones.
        """
        self.ensure_tables(manifest)
        for item in manifest["tables"]:
            if item.get("table") != table:
                continue
            item["existence"] = existence.value
            if entry is not None:
                item["entry"] = entry.model_dump(mode="json")
            if notes:
                item["notes"] = notes
            if deferred_questions is not None:
                item["deferred_questions"] = deferred_questions
            return manifest
        raise KeyError(f"unknown table: {table}")

    def mark_screenshots_done(
        self,
        manifest: dict[str, Any],
        table: str,
        images: Optional[list[str]] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Close the phase-3 screenshot round for one table.

        `screenshots_done` is what keeps a re-run from re-driving the browser
        for a table whose annotated images already exist - the same job
        `table_has_field_evidence` does for the field-mapping round.
        """
        self.ensure_tables(manifest)
        for item in manifest["tables"]:
            if item.get("table") != table:
                continue
            item["screenshots_done"] = True
            if images:
                item["annotated_images"] = images
            if notes:
                item["screenshot_notes"] = notes
            return manifest
        raise KeyError(f"unknown table: {table}")

    # ---------- evidence index ----------

    def load_evidence(self) -> dict[str, Any]:
        path = self.dir / EVIDENCE_INDEX
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def merge_evidence(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        index = self.load_evidence()
        index[table] = payload
        self.dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            self.dir / EVIDENCE_INDEX,
            json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        )
        return index

    # ---------- append-only notes ----------

    def append_blackboard(self, line: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / BLACKBOARD).open("a", encoding="utf-8") as fh:
            fh.write(line.rstrip() + "\n")

    def write_questions(self, questions: list[str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        body = "\n".join(f"- [ ] {q}" for q in questions)
        _atomic_write(self.dir / QUESTIONS, "# 待人工确认\n\n" + body + "\n")
