from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from skill_warden.models import Verdict


def decide(
    findings: Sequence[Mapping[str, str]],
    stages_requested: Collection[str],
    status: str,
) -> Verdict:
    """Pick BLOCK, ASK, or ALLOW. First match wins. No I/O and no clock."""
    stages = frozenset(stages_requested)
    if status == "timeout":
        return Verdict("BLOCK", "timeout")
    if status != "completed":
        return Verdict("BLOCK", "not_finished")
    if not findings:
        return Verdict("BLOCK", "no_findings")

    canary = _first(findings, source="canary")
    if canary is not None:
        return Verdict("BLOCK", "canary", canary["rule_id"])

    reader_error = _first(findings, source="reader", severity="error")
    if reader_error is not None:
        return Verdict("BLOCK", "reader_error", reader_error["rule_id"])

    other_error = _first(findings, severity="error", source_excluded="reader")
    if other_error is not None:
        return Verdict("BLOCK", "tool_error", other_error["rule_id"])

    high = _first(findings, severities=frozenset({"high", "critical"}))
    if high is not None:
        return Verdict("BLOCK", "high_finding", high["rule_id"])

    if "static" in stages and not _stage_reported(findings, "semgrep"):
        return Verdict("BLOCK", "semgrep_missing")
    if "reader" in stages and not _stage_reported(findings, "reader"):
        return Verdict("BLOCK", "reader_missing")
    if "detonation" in stages and not _stage_reported(findings, "jail"):
        return Verdict("BLOCK", "detonation_missing")

    medium = _first(findings, severity="medium")
    if medium is not None:
        return Verdict("ASK", "medium_only", medium["rule_id"])
    return Verdict("ALLOW", "clean")


def _first(
    findings: Sequence[Mapping[str, str]],
    *,
    source: str | None = None,
    source_excluded: str | None = None,
    severity: str | None = None,
    severities: frozenset[str] | None = None,
) -> Mapping[str, str] | None:
    for finding in findings:
        if source is not None and finding["source"] != source:
            continue
        if source_excluded is not None and finding["source"] == source_excluded:
            continue
        if severity is not None and finding["severity"] != severity:
            continue
        if severities is not None and finding["severity"] not in severities:
            continue
        return finding
    return None


def _stage_reported(findings: Sequence[Mapping[str, str]], source: str) -> bool:
    return any(
        finding["source"] == source and finding["severity"] != "error"
        for finding in findings
    )
