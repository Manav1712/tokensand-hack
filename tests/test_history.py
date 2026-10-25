import json
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from skill_warden.hashing import content_hash
from skill_warden.models import Report, Verdict
from skill_warden.paths import data_dir
from skill_warden.pipeline import scan, scan_skill

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison"
_COLUMNS = (
    "run_id",
    "skill_path",
    "content_sha256",
    "decision",
    "reason",
    "report_json",
    "created_at",
)


def _rows(home: Path) -> list[dict[str, str | None]]:
    database = home / "history.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        found = conn.execute(
            """
            SELECT run_id, skill_path, content_sha256, decision, reason, report_json, created_at
            FROM runs
            ORDER BY rowid
            """
        ).fetchall()
    return [{key: row[key] for key in _COLUMNS} for row in found]


def _assert_row(row: dict[str, str | None], path: Path, report: Report) -> None:
    assert row["skill_path"] == str(path)
    assert row["content_sha256"] == content_hash(path)
    assert row["decision"] == report.verdict.decision
    assert row["reason"] == report.verdict.reason
    uuid.UUID(str(row["run_id"]))
    created = datetime.fromisoformat(str(row["created_at"]))
    assert created.tzinfo is not None
    assert abs((datetime.now(UTC) - created).total_seconds()) < 120
    body = json.loads(str(row["report_json"]))
    assert body == {
        "findings": [finding.to_row() for finding in report.findings],
        "verdict": {
            "decision": report.verdict.decision,
            "reason": report.verdict.reason,
            "detail": report.verdict.detail,
        },
    }


def test_data_dir_prefers_skill_warden_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "custom"
    monkeypatch.setenv("SKILL_WARDEN_HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert data_dir() == home


def test_data_dir_uses_xdg_when_home_is_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SKILL_WARDEN_HOME", raising=False)
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))

    assert data_dir() == xdg / "skill-warden"


def test_empty_skill_warden_home_is_unset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SKILL_WARDEN_HOME", "")
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))

    assert data_dir() == xdg / "skill-warden"


def test_data_dir_defaults_to_local_share(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SKILL_WARDEN_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert data_dir() == tmp_path / ".local" / "share" / "skill-warden"


def test_data_dir_uses_localappdata_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SKILL_WARDEN_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    local = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(sys, "platform", "win32")

    assert data_dir() == local / "skill-warden"


def test_scan_appends_one_row(history_home: Path) -> None:
    report = scan_skill(CLEAN)

    rows = _rows(history_home)
    assert len(rows) == 1
    _assert_row(rows[0], CLEAN, report)
    assert report.verdict == Verdict("ALLOW", "clean", "")


def test_second_scan_appends_another_row(history_home: Path) -> None:
    first = scan_skill(CLEAN)
    second = scan_skill(CLEAN)

    rows = _rows(history_home)
    assert len(rows) == 2
    assert rows[0]["run_id"] != rows[1]["run_id"]
    _assert_row(rows[0], CLEAN, first)
    _assert_row(rows[1], CLEAN, second)


def test_scan_of_two_paths_appends_two_rows(history_home: Path) -> None:
    reports = scan([CLEAN, MEMORY])

    rows = _rows(history_home)
    assert len(rows) == 2
    _assert_row(rows[0], CLEAN, reports[0])
    _assert_row(rows[1], MEMORY, reports[1])
    assert rows[1]["decision"] == "BLOCK"
    assert rows[1]["reason"] == "high_finding"


def test_no_history_does_not_create_a_database(history_home: Path) -> None:
    scan_skill(CLEAN, history=False)
    scan([CLEAN], history=False)

    assert not (history_home / "history.sqlite3").exists()


def test_no_history_leaves_existing_rows(history_home: Path) -> None:
    scan_skill(CLEAN)
    before = _rows(history_home)

    scan_skill(CLEAN, history=False)
    scan([MEMORY], history=False)

    assert _rows(history_home) == before
    assert len(before) == 1


def test_failed_write_warns_and_keeps_the_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SKILL_WARDEN_HOME", str(blocker))

    quiet = scan_skill(CLEAN, history=False)
    capsys.readouterr()
    saved = scan_skill(CLEAN)

    captured = capsys.readouterr()
    assert saved == quiet
    warning = next(
        line
        for line in captured.err.splitlines()
        if line.startswith("warning: history was not saved:")
    )
    assert "Format the current date" not in warning
    assert "YYYY-MM-DD" not in warning


def test_failure_before_the_hash_stores_null(
    monkeypatch: pytest.MonkeyPatch,
    history_home: Path,
) -> None:
    def boom(path: Path) -> str:
        raise RuntimeError(f"hash failed for {path.name}")

    monkeypatch.setattr("skill_warden.pipeline.content_hash", boom)

    report = scan_skill(CLEAN)

    rows = _rows(history_home)
    assert report == Report((), Verdict("BLOCK", "not_finished"))
    assert len(rows) == 1
    assert rows[0]["content_sha256"] is None
    assert rows[0]["decision"] == "BLOCK"
    assert rows[0]["reason"] == "not_finished"
    assert rows[0]["skill_path"] == str(CLEAN)
