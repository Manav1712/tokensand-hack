from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from skill_warden.findings import build_rows
from skill_warden.hashing import content_hash
from skill_warden.history import record
from skill_warden.jail import detonate as jail_detonate
from skill_warden.memory_store import MemoryStore
from skill_warden.models import Finding, Report, Verdict
from skill_warden.policy import decide
from skill_warden.reader import ReaderResult
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import rule_path
from skill_warden.semgrep import scan as semgrep_scan

_STATIC = frozenset({"static"})


def scan_skill(
    path: Path,
    *,
    llm: object = None,
    detonate: bool = False,
    history: bool = True,
    secrets: Sequence[str] | None = None,
) -> Report:
    content_sha256: str | None = None
    redactions = list(secrets or ())
    try:
        content_sha256 = content_hash(Path(path))
        report = _scan_skill(
            path,
            content_sha256,
            llm=llm,
            detonate=detonate,
            redactions=redactions,
        )
    except Exception:  # noqa: BLE001
        report = Report((), Verdict("BLOCK", "not_finished"))
    if history:
        _save_history(path, report, content_sha256, redactions)
    return report


def scan(
    paths: Sequence[Path],
    *,
    llm: object = None,
    detonate: bool = False,
    history: bool = True,
    secrets: Sequence[str] | None = None,
) -> tuple[Report, ...]:
    return tuple(
        scan_skill(path, llm=llm, detonate=detonate, history=history, secrets=secrets)
        for path in paths
    )


def _save_history(
    path: Path,
    report: Report,
    content_sha256: str | None,
    redactions: Sequence[str],
) -> None:
    try:
        record(path, report, content_sha256, redactions)
    except (sqlite3.Error, OSError):
        print("history write failed", file=sys.stderr)


def _scan_skill(
    path: Path,
    skill_hash: str,
    *,
    llm: object,
    detonate: bool,
    redactions: list[str],
) -> Report:
    root = Path(path)
    files = _skill_files(root)
    semgrep_report = semgrep_scan(files, rule_path())
    reader_body = _reader_body(llm, files) if llm is not None else None
    if not detonate:
        rows = build_rows(semgrep=semgrep_report, reader=reader_body, secrets=redactions)
        return _report(rows)
    return _detonate(root, skill_hash, reader_body, redactions)


def _detonate(root: Path, skill_hash: str, reader_body: object, redactions: list[str]) -> Report:
    nonce = secrets.token_hex(16)
    store = MemoryStore(secrets=[nonce])
    record = SkillRecord(
        publisher="local",
        name=root.name,
        version="0",
        path=root,
        content_hash=skill_hash,
    )
    run_id = uuid4()
    with TemporaryDirectory() as scratch:
        jail_detonate(
            record,
            store,
            run_id=run_id,
            nonce=nonce,
            rules=rule_path(),
            scratch=Path(scratch),
        )
    if reader_body is not None:
        store.insert_findings(run_id, build_rows(reader=reader_body, secrets=redactions))
    decision, reason = store.verdict(run_id)
    rows = store._findings.get(run_id, [])
    findings = tuple(Finding.from_row(row) for row in rows)
    return Report(findings, Verdict(decision, reason))


def _report(rows: list[dict[str, str]]) -> Report:
    verdict = decide(rows, _STATIC, "completed")
    findings = tuple(Finding.from_row(row) for row in rows)
    return Report(findings, verdict)


def _reader_body(llm: object, files: list[Path]) -> object:
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    result = llm.call(text)  # type: ignore[attr-defined]
    if isinstance(result, ReaderResult):
        return {"flags": list(result.flags), "evidence": list(result.evidence)}
    return result


def _skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if name == "HASH" or path.is_symlink() or not path.is_file():
                continue
            files.append(path)
    return sorted(files)
