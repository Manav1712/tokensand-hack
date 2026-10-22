import hashlib
from dataclasses import FrozenInstanceError

import pytest

from skill_warden.findings import build_rows
from skill_warden.models import Finding, Report, Severity, Source, Verdict

_ROW_KEYS = ("source", "rule_id", "severity", "file", "excerpt", "evidence_hash")


def _result(check_id: str, path: str, severity: str, message: str) -> dict:
    return {
        "check_id": check_id,
        "path": path,
        "extra": {"severity": severity, "message": message},
    }


def _semgrep(results: list[dict], errors: list | None = None, skipped: list | None = None) -> dict:
    return {
        "results": results,
        "errors": [] if errors is None else errors,
        "paths": {"skipped": [] if skipped is None else skipped},
    }


def _scanner_rows() -> list[dict[str, str]]:
    semgrep = build_rows(
        semgrep=_semgrep(
            [_result("rules.a", "SKILL.md", "ERROR", "alpha")],
            skipped=[{"path": "pkg/SKILL.md"}],
        )
    )
    reader = build_rows(
        reader={"flags": ["credential_exfil", "obfuscation"], "evidence": ["sent the note"]}
    )
    canary = build_rows(canary_log="posted")
    policy = build_rows(rules_requested=["p/agent-skills"], rules_loaded=0)
    jail = build_rows(jail_events=[{"kind": "connect", "dst": "203.0.113.9"}], sink="10.0.0.2")
    return semgrep + reader + canary + policy + jail


def test_scanner_rows_round_trip_every_key():
    rows = _scanner_rows()
    assert {row["source"] for row in rows} == {"semgrep", "reader", "canary", "policy", "jail"}

    for row in rows:
        finding = Finding.from_row(row)
        assert finding.to_row() == row
        assert tuple(finding.to_row()) == _ROW_KEYS
        assert finding.evidence_hash == hashlib.sha256(row["excerpt"].encode()).hexdigest()
        assert finding.source == row["source"]
        assert finding.severity == row["severity"]
        assert Finding.from_row(row) == finding


def test_line_round_trips_when_the_row_has_one():
    row = dict(_scanner_rows()[0])
    row["line"] = 8

    finding = Finding.from_row(row)

    assert finding.line == 8
    assert finding.to_row() == row
    assert Finding.from_row(row).to_row()["line"] == 8


def test_mismatched_evidence_hash_is_rejected():
    row = dict(_scanner_rows()[0])
    row["evidence_hash"] = "0" * 64

    with pytest.raises(ValueError):
        Finding.from_row(row)


def test_unknown_source_is_rejected():
    row = dict(_scanner_rows()[0])
    row["source"] = "oracle"

    with pytest.raises(ValueError):
        Finding.from_row(row)


def test_source_and_severity_values():
    assert {item.value for item in Source} == {
        "intake",
        "semgrep",
        "reader",
        "jail",
        "canary",
        "policy",
    }
    assert {item.value for item in Severity} == {
        "info",
        "low",
        "medium",
        "high",
        "critical",
        "error",
    }


def test_finding_verdict_and_report_are_frozen():
    finding = Finding.from_row(_scanner_rows()[0])
    verdict = Verdict("BLOCK", "high_finding", "rules.a")
    report = Report((finding,), verdict)

    with pytest.raises(FrozenInstanceError):
        finding.rule_id = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        verdict.reason = "clean"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.verdict = Verdict("ALLOW", "clean")  # type: ignore[misc]

    assert report.findings == (finding,)
    assert report.verdict.decision == "BLOCK"
    assert report.verdict.detail == "rules.a"


def test_report_copies_findings_into_a_tuple():
    finding = Finding.from_row(build_rows(canary_log="posted")[0])
    verdict = Verdict("BLOCK", "canary")
    held = [finding]

    report = Report(held, verdict)
    held.clear()

    assert report.findings == (finding,)
    assert report.verdict.detail == ""


def test_verdict_rejects_an_unknown_decision():
    with pytest.raises(ValueError):
        Verdict("MAYBE", "clean")
