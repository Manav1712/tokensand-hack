from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

_ROW_KEYS = ("source", "rule_id", "severity", "file", "excerpt", "evidence_hash")
_DECISIONS = frozenset({"BLOCK", "ASK", "ALLOW"})


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
        for key in ("rule_id", "file", "excerpt", "evidence_hash"):
            if not isinstance(row[key], str):
                raise TypeError(f"{key} must be a str")
        return cls(
            source=Source(row["source"]),
            rule_id=row["rule_id"],
            severity=Severity(row["severity"]),
            file=row["file"],
            line=line,
            excerpt=row["excerpt"],
            evidence_hash=row["evidence_hash"],
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


@dataclass(frozen=True)
class Verdict:
    decision: Literal["BLOCK", "ASK", "ALLOW"]
    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.decision not in _DECISIONS:
            raise ValueError("decision must be BLOCK, ASK, or ALLOW")


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]
    verdict: Verdict

    def __post_init__(self) -> None:
        findings = tuple(self.findings)
        if any(not isinstance(item, Finding) for item in findings):
            raise TypeError("findings must be Finding values")
        if not isinstance(self.verdict, Verdict):
            raise TypeError("verdict must be a Verdict")
        object.__setattr__(self, "findings", findings)
