from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from skill_warden.models import Report
from skill_warden.paths import data_dir

_CREATE = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  skill_path TEXT NOT NULL,
  content_sha256 TEXT,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  report_json TEXT NOT NULL,
  created_at TEXT NOT NULL
)
"""

_INSERT = """
INSERT INTO runs (
  run_id, skill_path, content_sha256, decision, reason, report_json, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def record(path: Path, report: Report, content_sha256: str | None) -> None:
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "findings": [finding.to_row() for finding in report.findings],
        "verdict": {
            "decision": report.verdict.decision,
            "reason": report.verdict.reason,
            "detail": report.verdict.detail,
        },
    }
    with sqlite3.connect(directory / "history.sqlite3") as conn:
        conn.execute(_CREATE)
        conn.execute(
            _INSERT,
            (
                str(uuid4()),
                os.fspath(Path(path)),
                content_sha256,
                report.verdict.decision,
                report.verdict.reason,
                json.dumps(payload, sort_keys=True),
                datetime.now(UTC).isoformat(),
            ),
        )
