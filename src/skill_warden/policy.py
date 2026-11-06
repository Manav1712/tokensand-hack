from __future__ import annotations

from collections.abc import Sequence

from skill_warden.models import Approval, Finding, RunOutcome, Severity, Source, Verdict

_HIGH = frozenset({Severity.HIGH, Severity.CRITICAL})


def block_not_finished() -> Verdict:
    """A stage raised, so the run did not finish. Does not call decide()."""
    return Verdict("BLOCK", "not_finished")


def decide(outcome: RunOutcome, approval: Approval | None = None) -> Verdict:
    """Pick BLOCK, ASK, or ALLOW. First match wins. No I/O and no clock.

    ``approval`` is unused until covered findings arrive in M5-01. Until then
    every finding is uncovered.
    """
    if outcome.status == "timeout":
        return Verdict("BLOCK", "timeout")
    if outcome.status != "completed":
        return block_not_finished()
    if not outcome.findings:
        return Verdict("BLOCK", "no_findings")

    canary = _first(outcome.findings, source=Source.CANARY)
    if canary is not None:
        return Verdict("BLOCK", "canary", canary.rule_id)

    reader_error = _first(outcome.findings, source=Source.READER, severity=Severity.ERROR)
    if reader_error is not None:
        return Verdict("BLOCK", "reader_error", reader_error.rule_id)

    other_error = _first(outcome.findings, severity=Severity.ERROR)
    if other_error is not None:
        return Verdict("BLOCK", "tool_error", other_error.rule_id)

    high = _first(outcome.findings, severities=_HIGH)
    if high is not None:
        return Verdict("BLOCK", "high_finding", high.rule_id)

    if "static" in outcome.stages_requested and not _stage_reported(
        outcome.findings, Source.SEMGREP
    ):
        return Verdict("BLOCK", "semgrep_missing")
    if "reader" in outcome.stages_requested and not _stage_reported(
        outcome.findings, Source.READER
    ):
        return Verdict("BLOCK", "reader_missing")
    if "detonation" in outcome.stages_requested and not _stage_reported(
        outcome.findings, Source.JAIL
    ):
        return Verdict("BLOCK", "detonation_missing")

    medium = _first(outcome.findings, severity=Severity.MEDIUM)
    if medium is not None:
        return Verdict("ASK", "medium_only", medium.rule_id)
    return Verdict("ALLOW", "clean")


def _first(
    findings: Sequence[Finding],
    *,
    source: Source | None = None,
    severity: Severity | None = None,
    severities: frozenset[Severity] | None = None,
) -> Finding | None:
    for finding in findings:
        if source is not None and finding.source != source:
            continue
        if severity is not None and finding.severity != severity:
            continue
        if severities is not None and finding.severity not in severities:
            continue
        return finding
    return None


def _stage_reported(findings: Sequence[Finding], source: Source) -> bool:
    return any(
        finding.source == source and finding.severity != Severity.ERROR
        for finding in findings
    )
