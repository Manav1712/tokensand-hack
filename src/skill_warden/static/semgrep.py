"""Fail-closed Semgrep stage."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from skill_warden.models import Finding, Severity, Source, StageResult
from skill_warden.redact import excerpt

DEFAULT_TIMEOUT = 60
_PER_TARGET_TIMEOUT = "20"
_ENV_KEYS = ("PATH", "HOME", "LANG")
_HIGH = {"ERROR", "CRITICAL", "HIGH"}
_MEDIUM = {"WARNING", "MEDIUM"}


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    timed_out: bool = False


Runner = Callable[[Sequence[str], Path, Mapping[str, str], float], Completed]


def binary_name() -> str:
    if os.name == "nt":
        return "semgrep.exe"
    return "semgrep"


def resolve_binary(
    configured: Path | None,
    executable: Path,
    which: Callable[[str], str | None],
) -> Path | None:
    """Configured path, then the interpreter's directory, then PATH."""
    if configured is not None:
        if configured.is_file():
            return configured
        return None
    sibling = executable.parent / binary_name()
    if sibling.is_file():
        return sibling
    found = which(binary_name())
    if found is None:
        return None
    return Path(found)


def scan(
    files: Sequence[Path],
    rules: Sequence[Path],
    workdir: Path,
    *,
    configured: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    run: Runner | None = None,
    executable: Path | None = None,
    which: Callable[[str], str | None] | None = None,
) -> StageResult:
    """Scan explicit text files. A directory is never a target."""
    started = time.monotonic()
    workdir.mkdir(parents=True, exist_ok=True)
    liveness = _liveness_file(workdir)
    targets = [path for path in files if path.is_file()]
    targets.append(liveness)
    binary = resolve_binary(
        configured,
        Path(sys.executable) if executable is None else executable,
        shutil.which if which is None else which,
    )
    if binary is None:
        return _result(
            "failed",
            (_finding("semgrep_unavailable", Severity.ERROR, "reinstall skill-warden"),),
            "semgrep_unavailable",
            started,
        )
    argv = _argv(binary, rules, targets)
    env = _child_env()
    runner = _default_run if run is None else run
    try:
        completed = runner(argv, workdir, env, timeout)
    except subprocess.TimeoutExpired:
        return _result(
            "timeout",
            (_finding("semgrep_timeout", Severity.ERROR),),
            "semgrep_timeout",
            started,
        )
    except Exception:  # noqa: BLE001
        return _result(
            "failed",
            (_finding("semgrep_failed", Severity.ERROR, "run"),),
            "run",
            started,
        )
    return _interpret(completed, targets, liveness, started)


def _liveness_file(workdir: Path) -> Path:
    nonce = secrets.token_hex(8)
    path = workdir / f".warden-liveness-{nonce}.txt"
    path.write_text(f"WARDEN-LIVENESS-{nonce}\n", encoding="utf-8")
    return path


def _argv(binary: Path, rules: Sequence[Path], targets: Sequence[Path]) -> list[str]:
    argv = [
        str(binary),
        "scan",
        "--json",
        "--metrics=off",
        "--disable-version-check",
        "--scan-unknown-extensions",
        "--timeout",
        _PER_TARGET_TIMEOUT,
    ]
    for rule in rules:
        argv.extend(["--config", str(rule)])
    argv.extend(str(target) for target in targets)
    return argv


def _child_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


def _default_run(
    argv: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
) -> Completed:
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Completed(0, "", True)
    return Completed(completed.returncode, completed.stdout, False)


def _interpret(
    completed: Completed,
    targets: Sequence[Path],
    liveness: Path,
    started: float,
) -> StageResult:
    if completed.timed_out:
        return _result(
            "timeout",
            (_finding("semgrep_timeout", Severity.ERROR),),
            "semgrep_timeout",
            started,
        )
    if completed.returncode != 0:
        detail = str(completed.returncode)
        return _result(
            "failed",
            (_finding("semgrep_failed", Severity.ERROR, detail),),
            detail,
            started,
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _result(
            "failed",
            (_finding("semgrep_failed", Severity.ERROR, "stdout"),),
            "stdout",
            started,
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return _result(
            "failed",
            (_finding("semgrep_failed", Severity.ERROR, "stdout"),),
            "stdout",
            started,
        )
    findings = _error_findings(payload)
    results = payload["results"]
    liveness_hits = [item for item in results if _is_liveness(item, liveness)]
    if len(liveness_hits) != 1:
        findings.append(_finding("semgrep_liveness_failed", Severity.ERROR))
    scanned = _scanned(payload)
    for target in targets:
        if not _was_scanned(target, scanned):
            findings.append(_finding("target_not_scanned", Severity.ERROR, target.name))
    saw_real = False
    for item in results:
        if not isinstance(item, dict):
            findings.append(_finding("semgrep_failed", Severity.ERROR, "result"))
            continue
        if item in liveness_hits:
            continue
        saw_real = True
        findings.append(_result_finding(item))
    if _clean(findings) and not saw_real:
        findings.append(_finding("semgrep.ok", Severity.INFO))
    status: Literal["ok", "failed"] = "ok" if _clean(findings) else "failed"
    detail = ""
    for finding in findings:
        if finding.severity is Severity.ERROR:
            detail = finding.rule_id
            break
    return _result(status, tuple(findings), detail, started)


def _clean(findings: Sequence[Finding]) -> bool:
    return not any(finding.severity is Severity.ERROR for finding in findings)


def _error_findings(payload: Mapping[str, object]) -> list[Finding]:
    findings: list[Finding] = []
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return findings
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        level = str(entry.get("level") or "").lower()
        if level == "error":
            findings.append(_finding("semgrep_error", Severity.ERROR))
        elif level == "warn":
            findings.append(_finding("semgrep_warning", Severity.INFO))
    return findings


def _scanned(payload: Mapping[str, object]) -> set[str]:
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return set()
    raw = paths.get("scanned")
    if not isinstance(raw, list):
        return set()
    return {str(Path(str(item)).resolve()) for item in raw}


def _was_scanned(target: Path, scanned: set[str]) -> bool:
    return str(target.resolve()) in scanned


def _is_liveness(item: object, liveness: Path) -> bool:
    if not isinstance(item, dict):
        return False
    path = item.get("path")
    if isinstance(path, str) and Path(path).name == liveness.name:
        return True
    check = item.get("check_id")
    if not isinstance(check, str):
        return False
    return check == "warden-liveness" or check.endswith(".warden-liveness")


def _result_finding(item: Mapping[str, object]) -> Finding:
    extra = item.get("extra")
    if not isinstance(extra, dict):
        extra = {}
    start = item.get("start")
    line = start.get("line") if isinstance(start, dict) else None
    if isinstance(line, bool) or not isinstance(line, int):
        line = None
    check = item.get("check_id")
    path = item.get("path")
    message = extra.get("message")
    return Finding(
        Source.SEMGREP,
        check if isinstance(check, str) else "",
        _severity(str(extra.get("severity") or "")),
        file=path if isinstance(path, str) else "",
        line=line,
        excerpt=excerpt(message if isinstance(message, str) else ""),
    )


def _severity(raw: str) -> Severity:
    key = raw.strip().upper()
    if key in _HIGH:
        return Severity.HIGH
    if key in _MEDIUM:
        return Severity.MEDIUM
    if key == "LOW":
        return Severity.LOW
    if key == "INFO":
        return Severity.INFO
    return Severity.ERROR


def _finding(rule_id: str, severity: Severity, text: str = "") -> Finding:
    return Finding(Source.SEMGREP, rule_id, severity, excerpt=text)


def _result(
    status: Literal["ok", "failed", "timeout"],
    findings: tuple[Finding, ...],
    detail: str,
    started: float,
) -> StageResult:
    return StageResult(
        "static",
        status,
        findings,
        detail=detail,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
