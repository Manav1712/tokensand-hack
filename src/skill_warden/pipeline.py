"""Scan a skill through intake, static, an optional reader, and optional detonation."""

from __future__ import annotations

import sqlite3
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal
from uuid import uuid4

from skill_warden.findings import build_rows
from skill_warden.intake import LoadedSkill, load_skill, write_normalized
from skill_warden.models import (
    Finding,
    Report,
    RunOutcome,
    Severity,
    Source,
    Stage,
    StageResult,
)
from skill_warden.policy import block_not_finished, decide
from skill_warden.reader import ReaderResult
from skill_warden.redact import contains_secret, redact
from skill_warden.static.semgrep import rule_path
from skill_warden.static.semgrep import scan as static_scan

_READER_LIMIT = 60_000
_STAGE_LIMIT = 60.0
_SAFETY = 60.0
Clock = Callable[[], float]


def scan_skill(
    path: Path,
    *,
    llm: object = None,
    detonate: bool = False,
    history: bool = True,
    full: bool = False,
    timeout: float | Literal["auto"] = "auto",
    clock: Clock | None = None,
) -> Report:
    content_sha256: str | None = None
    try:
        report, content_sha256 = _scan_skill(
            path,
            llm=llm,
            detonate=detonate,
            full=full,
            timeout=timeout,
            clock=time.monotonic if clock is None else clock,
        )
    except Exception:  # noqa: BLE001
        report = Report((), block_not_finished())
    if history:
        _save_history(path, report, content_sha256)
    return report


def scan(
    paths: Sequence[Path],
    *,
    llm: object = None,
    detonate: bool = False,
    history: bool = True,
    full: bool = False,
    timeout: float | Literal["auto"] = "auto",
    clock: Clock | None = None,
) -> tuple[Report, ...]:
    return tuple(
        scan_skill(
            path,
            llm=llm,
            detonate=detonate,
            history=history,
            full=full,
            timeout=timeout,
            clock=clock,
        )
        for path in paths
    )


def guarded_render(text: str, secrets: Sequence[str]) -> str:
    """Replace text that still contains a run secret. The secret is not returned."""
    if contains_secret(text, list(secrets)):
        return "BLOCK not_finished\n"
    return text


def _save_history(path: Path, report: Report, content_sha256: str | None) -> None:
    try:
        from skill_warden.history import record

        record(path, report, content_sha256)
    except (sqlite3.Error, OSError) as exc:
        print(f"warning: history was not saved: {exc}", file=sys.stderr)


def _scan_skill(
    path: Path,
    *,
    llm: object,
    detonate: bool,
    full: bool,
    timeout: float | Literal["auto"],
    clock: Clock,
) -> tuple[Report, str | None]:
    started = clock()
    deadline = started + (_auto_limit(llm is not None, detonate) if timeout == "auto" else timeout)
    timings: list[tuple[str, int]] = []
    findings: list[Finding] = []
    coverage: list[StageResult] = []
    secrets: list[str] = _reader_secret(llm)

    intake_started = clock()
    if _expired(clock, deadline):
        return _timeout_report(path, findings, coverage, timings, started, clock)
    loaded = load_skill(Path(path))
    timings.append(("intake", _elapsed(intake_started, clock)))
    findings.extend(loaded.findings)
    blocked = _stop(findings)
    work = Path(mkdtemp())
    try:
        if not blocked:
            norm_started = clock()
            findings.extend(write_normalized(loaded.record.path, loaded.record.files, work))
            timings.append(("normalize", _elapsed(norm_started, clock)))
        static_result = _static(loaded, work, deadline, clock, skip=blocked)
        coverage.append(static_result)
        findings.extend(static_result.findings)
        timings.append(("static", static_result.elapsed_ms))
        reader_skip = blocked or (not full and _stop(findings)) or llm is None
        if llm is None:
            coverage.append(_skipped("reader"))
        else:
            reader_result = _reader(llm, loaded, work, deadline, clock, skip=reader_skip)
            coverage.append(reader_result)
            findings.extend(reader_result.findings)
            timings.append(("reader", reader_result.elapsed_ms))
        detonate_skip = not detonate or (not full and _stop(findings))
        if not detonate:
            coverage.append(_skipped("detonation"))
        else:
            detonate_result, nonce = _detonate(
                loaded,
                deadline,
                clock,
                skip=detonate_skip,
            )
            if nonce:
                secrets.append(nonce)
            coverage.append(detonate_result)
            findings.extend(detonate_result.findings)
            timings.append(("detonation", detonate_result.elapsed_ms))
    finally:
        _remove_tree(work)
    status: Literal["completed", "timeout"] = "timeout" if _expired(clock, deadline) else "completed"
    redacted = _redact(findings, secrets)
    stages = _requested(llm is not None, detonate)
    outcome = RunOutcome(
        uuid4(),
        status,
        stages,
        tuple(redacted),
        loaded.record.content_sha256,
        loaded.record.hash_version,
    )
    verdict = decide(outcome)
    report = Report(
        tuple(redacted),
        verdict,
        skill=loaded.record,
        outcome=outcome,
        coverage=tuple(coverage),
        timings_ms=tuple(timings),
    )
    return report, loaded.record.content_sha256


def _static(
    loaded: LoadedSkill,
    work: Path,
    deadline: float,
    clock: Clock,
    *,
    skip: bool,
) -> StageResult:
    if skip or _expired(clock, deadline):
        return _skipped("static") if skip else _timed_out("static")
    started = clock()
    try:
        targets = [
            work / entry.relpath
            for entry in loaded.record.files
            if entry.kind == "text" and (work / entry.relpath).is_file()
        ]
        result = static_scan(targets, [rule_path(), _liveness_path()], work)
    except Exception:  # noqa: BLE001
        result = StageResult(
            "static",
            "failed",
            (_finding(Source.SEMGREP, "semgrep_failed", Severity.ERROR),),
        )
    return _with_elapsed(result, started, clock)


def _reader(
    llm: object,
    loaded: LoadedSkill,
    work: Path,
    deadline: float,
    clock: Clock,
    *,
    skip: bool,
) -> StageResult:
    if skip or _expired(clock, deadline):
        return _skipped("reader") if skip else _timed_out("reader")
    started = clock()
    try:
        parts = [
            (work / entry.relpath).read_text(encoding="utf-8")
            for entry in loaded.record.files
            if entry.kind == "text" and (work / entry.relpath).is_file()
        ]
        text = "\n".join(parts)
        if len(text) > _READER_LIMIT:
            result = StageResult(
                "reader",
                "failed",
                (_finding(Source.READER, "reader_input_too_large", Severity.ERROR),),
            )
        else:
            result = StageResult("reader", "ok", _reader_findings(llm, text))
    except Exception:  # noqa: BLE001
        result = StageResult(
            "reader",
            "failed",
            (_finding(Source.READER, "reader_unavailable", Severity.ERROR),),
        )
    return _with_elapsed(result, started, clock)


def _reader_findings(llm: object, text: str) -> tuple[Finding, ...]:
    called = llm.call(text)  # type: ignore[attr-defined]
    if isinstance(called, ReaderResult):
        body: object = {"flags": list(called.flags), "evidence": list(called.evidence)}
    else:
        body = called
    rows = build_rows(reader=body)
    if not rows:
        return (_finding(Source.READER, "reader.ok", Severity.INFO),)
    return tuple(Finding.from_row(row) for row in rows)


def _detonate(
    loaded: LoadedSkill,
    deadline: float,
    clock: Clock,
    *,
    skip: bool,
) -> tuple[StageResult, str]:
    if skip or _expired(clock, deadline):
        return (_skipped("detonation") if skip else _timed_out("detonation"), "")
    started = clock()
    result = StageResult(
        "detonation",
        "failed",
        (_finding(Source.JAIL, "detonation_unavailable", Severity.ERROR),),
    )
    return _with_elapsed(result, started, clock), ""


def _timeout_report(
    path: Path,
    findings: Sequence[Finding],
    coverage: Sequence[StageResult],
    timings: Sequence[tuple[str, int]],
    started: float,
    clock: Clock,
) -> tuple[Report, None]:
    outcome = RunOutcome(uuid4(), "timeout", frozenset(("static",)), tuple(findings), None, 2)
    report = Report(
        tuple(findings),
        decide(outcome),
        outcome=outcome,
        coverage=tuple(coverage),
        timings_ms=(*timings, ("clock", _elapsed(started, clock))),
    )
    del path
    return report, None


def _reader_secret(llm: object) -> list[str]:
    secret = getattr(llm, "api_key", None)
    if isinstance(secret, str) and secret:
        return [secret]
    return []


def _redact(findings: Sequence[Finding], secrets: Sequence[str]) -> tuple[Finding, ...]:
    cleaned: list[Finding] = []
    for finding in findings:
        text = redact(finding.excerpt, list(secrets))
        cleaned.append(
            Finding(
                finding.source,
                finding.rule_id,
                finding.severity,
                file=finding.file,
                line=finding.line,
                excerpt=text,
            )
        )
    return tuple(cleaned)


def _stop(findings: Sequence[Finding]) -> bool:
    return any(
        finding.source is Source.CANARY
        or finding.severity in {Severity.ERROR, Severity.HIGH, Severity.CRITICAL}
        for finding in findings
    )


def _requested(reader: bool, detonate: bool) -> frozenset[Stage]:
    stages: set[Stage] = {"static"}
    if reader:
        stages.add("reader")
    if detonate:
        stages.add("detonation")
    return frozenset(stages)


def _auto_limit(reader: bool, detonate: bool) -> float:
    limit = _STAGE_LIMIT + _SAFETY
    if reader:
        limit += _STAGE_LIMIT
    if detonate:
        limit += _STAGE_LIMIT
    return limit


def _expired(clock: Clock, deadline: float) -> bool:
    return clock() >= deadline


def _elapsed(started: float, clock: Clock) -> int:
    return max(0, int((clock() - started) * 1000))


def _skipped(stage: Stage) -> StageResult:
    return StageResult(stage, "skipped", ())


def _timed_out(stage: Stage) -> StageResult:
    return StageResult(stage, "timeout", (_finding(Source.SEMGREP, "timeout", Severity.ERROR),))


def _with_elapsed(result: StageResult, started: float, clock: Clock) -> StageResult:
    return StageResult(
        result.stage,
        result.status,
        result.findings,
        detail=result.detail,
        elapsed_ms=_elapsed(started, clock),
        secrets=result.secrets,
    )


def _finding(source: Source, rule_id: str, severity: Severity) -> Finding:
    return Finding(source, rule_id, severity)


def _liveness_path() -> Path:
    from importlib.resources import as_file, files

    resource = files("skill_warden").joinpath("rules", "liveness.yaml")
    with as_file(resource) as path:
        return Path(path)


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()
