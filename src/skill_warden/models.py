from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

_ROW_KEYS = ("source", "rule_id", "severity", "file", "excerpt", "evidence_hash")
_DECISIONS = frozenset({"BLOCK", "ASK", "ALLOW"})
_FILE_KINDS = frozenset({"text", "binary"})
_STAGES = frozenset({"static", "reader", "detonation"})
_STAGE_STATUSES = frozenset({"ok", "failed", "timeout", "skipped"})
_RUN_STATUSES = frozenset({"completed", "timeout", "error"})

Stage = Literal["static", "reader", "detonation"]


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    ERROR = "error"


class Source(StrEnum):
    INTAKE = "intake"
    SEMGREP = "semgrep"
    READER = "reader"
    JAIL = "jail"
    CANARY = "canary"
    # Hackathon scanner label. M2 stops emitting it; new findings use semgrep or intake.
    POLICY = "policy"


def _excerpt_hash(excerpt: str) -> str:
    return hashlib.sha256(excerpt.encode()).hexdigest()


def _text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a str")
    return value


@dataclass(frozen=True)
class Finding:
    source: Source
    rule_id: str
    severity: Severity
    file: str = ""
    line: int | None = None
    excerpt: str = ""
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.excerpt, str):
            raise TypeError("excerpt must be a str")
        digest = _excerpt_hash(self.excerpt)
        if self.evidence_hash == "":
            object.__setattr__(self, "evidence_hash", digest)
        elif self.evidence_hash != digest:
            raise ValueError("evidence_hash does not match excerpt")

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> Finding:
        missing = [key for key in _ROW_KEYS if key not in row]
        if missing:
            raise ValueError(f"finding row missing {', '.join(missing)}")
        line = row.get("line")
        if line is not None and (isinstance(line, bool) or not isinstance(line, int)):
            raise TypeError("line must be an int")
        # A non-string source or severity still reaches the enum, which raises ValueError.
        return cls(
            source=Source(cast(str, row["source"])),
            rule_id=_text(row, "rule_id"),
            severity=Severity(cast(str, row["severity"])),
            file=_text(row, "file"),
            line=line,
            excerpt=_text(row, "excerpt"),
            evidence_hash=_text(row, "evidence_hash"),
        )

    def to_row(self) -> dict[str, str | int]:
        row: dict[str, str | int] = {
            "source": self.source.value,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "file": self.file,
            "excerpt": self.excerpt,
            "evidence_hash": self.evidence_hash,
        }
        if self.line is not None:
            row["line"] = self.line
        return row


def _freeze_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    frozen = tuple(findings)
    if any(not isinstance(item, Finding) for item in frozen):
        raise TypeError("findings must be Finding values")
    return frozen


@dataclass(frozen=True)
class FileEntry:
    relpath: str
    size: int
    kind: Literal["text", "binary"]
    executable: bool

    def __post_init__(self) -> None:
        if self.kind not in _FILE_KINDS:
            raise ValueError("kind must be text or binary")


@dataclass(frozen=True)
class SkillRecord:
    path: Path
    name: str
    content_sha256: str | None
    hash_version: int
    files: tuple[FileEntry, ...]

    def __post_init__(self) -> None:
        files = tuple(self.files)
        if any(not isinstance(item, FileEntry) for item in files):
            raise TypeError("files must be FileEntry values")
        object.__setattr__(self, "files", files)


@dataclass(frozen=True)
class StageResult:
    stage: Stage
    status: Literal["ok", "failed", "timeout", "skipped"]
    findings: tuple[Finding, ...]
    detail: str = ""
    elapsed_ms: int = 0
    secrets: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if self.stage not in _STAGES:
            raise ValueError("stage must be static, reader, or detonation")
        if self.status not in _STAGE_STATUSES:
            raise ValueError("status must be ok, failed, timeout, or skipped")
        secrets = tuple(self.secrets)
        if any(not isinstance(item, str) for item in secrets):
            raise TypeError("secrets must be strings")
        object.__setattr__(self, "findings", _freeze_findings(self.findings))
        object.__setattr__(self, "secrets", secrets)

    def public(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "status": self.status,
            "findings": self.findings,
            "detail": self.detail,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class RunOutcome:
    run_id: UUID
    status: Literal["completed", "timeout", "error"]
    stages_requested: frozenset[Stage]
    findings: tuple[Finding, ...]
    content_sha256: str | None
    hash_version: int

    def __post_init__(self) -> None:
        if self.status not in _RUN_STATUSES:
            raise ValueError("status must be completed, timeout, or error")
        stages = frozenset(self.stages_requested)
        if not stages <= _STAGES:
            raise ValueError("stage must be static, reader, or detonation")
        object.__setattr__(self, "stages_requested", stages)
        object.__setattr__(self, "findings", _freeze_findings(self.findings))


@dataclass(frozen=True)
class Approval:
    id: str
    content_sha256: str
    hash_version: int
    accepted: frozenset[str]
    reason: str
    approved_at: str
    run_id: UUID

    def __post_init__(self) -> None:
        accepted = frozenset(self.accepted)
        if any(not isinstance(item, str) for item in accepted):
            raise TypeError("accepted must be rule ids")
        object.__setattr__(self, "accepted", accepted)


@dataclass(frozen=True)
class Verdict:
    decision: Literal["BLOCK", "ASK", "ALLOW"]
    reason: str
    detail: str = ""
    approval: Approval | None = None

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            raise ValueError("decision must be BLOCK, ASK, or ALLOW")
        if self.approval is not None and not isinstance(self.approval, Approval):
            raise TypeError("approval must be an Approval")


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]
    verdict: Verdict

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, Verdict):
            raise TypeError("verdict must be a Verdict")
        object.__setattr__(self, "findings", _freeze_findings(self.findings))
