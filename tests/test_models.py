import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest

from skill_warden.findings import build_rows
from skill_warden.models import (
    Approval,
    FileEntry,
    Finding,
    Report,
    RunOutcome,
    Severity,
    SkillRecord,
    Source,
    StageResult,
    Verdict,
)

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


def test_verdict_approval_defaults_to_none():
    verdict = Verdict("ALLOW", "clean")

    assert verdict.approval is None
    assert verdict.decision == "ALLOW"


def test_verdict_keeps_an_approval():
    approval = _approval()
    verdict = Verdict("ALLOW", "approved", "rule.a", approval)

    assert verdict.approval == approval
    assert verdict.detail == "rule.a"


def test_verdict_rejects_a_non_approval():
    with pytest.raises(TypeError):
        Verdict("ALLOW", "clean", approval="nope")  # type: ignore[arg-type]


def test_file_entry_accepts_text_and_binary():
    text = FileEntry("SKILL.md", 4, "text", False)
    binary = FileEntry("assets/icon.png", 8, "binary", True)

    assert text.kind == "text"
    assert text.executable is False
    assert binary.kind == "binary"
    assert binary.executable is True
    assert binary.size == 8


def test_file_entry_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        FileEntry("SKILL.md", 1, "image", False)


def test_skill_record_copies_files(tmp_path: Path):
    held = [FileEntry("SKILL.md", 4, "text", False)]
    record = SkillRecord(tmp_path, "date-helper", None, 2, held)
    held.clear()

    assert record.path == tmp_path
    assert record.name == "date-helper"
    assert record.content_sha256 is None
    assert record.hash_version == 2
    assert record.files == (FileEntry("SKILL.md", 4, "text", False),)

    hashed = SkillRecord(tmp_path, "date-helper", "abc", 2, ())
    assert hashed.content_sha256 == "abc"


def test_skill_record_rejects_a_non_file(tmp_path: Path):
    with pytest.raises(TypeError):
        SkillRecord(tmp_path, "date-helper", None, 2, ["SKILL.md"])  # type: ignore[list-item]


def test_stage_result_accepts_every_status():
    for status in ("ok", "failed", "timeout", "skipped"):
        result = StageResult("static", status, ())
        assert result.status == status
        assert result.stage == "static"
        assert result.detail == ""
        assert result.elapsed_ms == 0
        assert result.secrets == ()


def test_stage_result_rejects_a_bad_stage_or_status():
    with pytest.raises(ValueError):
        StageResult("intake", "ok", ())
    with pytest.raises(ValueError):
        StageResult("static", "off", ())


def test_stage_result_hides_secrets_and_copies_inputs():
    finding = _finding()
    findings = [finding]
    secrets = ["FAKE-CANARY"]
    result = StageResult("reader", "failed", findings, "reader_refused", 15, secrets)
    findings.clear()
    secrets.append("OTHER")

    assert result.findings == (finding,)
    assert result.secrets == ("FAKE-CANARY",)
    assert result.detail == "reader_refused"
    assert result.elapsed_ms == 15
    assert "FAKE-CANARY" not in repr(result)
    mapped = result.public()
    assert "secrets" not in mapped
    assert "FAKE-CANARY" not in repr(mapped)
    assert mapped["stage"] == "reader"
    assert mapped["status"] == "failed"
    assert mapped["findings"] == (finding,)
    assert mapped["detail"] == "reader_refused"
    assert mapped["elapsed_ms"] == 15

    same = StageResult("reader", "failed", (finding,), "reader_refused", 15, ("FAKE-CANARY",))
    other = StageResult("reader", "failed", (finding,), "reader_refused", 15, ("OTHER",))
    assert result == same
    assert result != other


def test_stage_result_rejects_a_non_finding():
    with pytest.raises(TypeError):
        StageResult("static", "ok", ["nope"])  # type: ignore[list-item]


def test_stage_result_rejects_a_non_string_secret():
    with pytest.raises(TypeError):
        StageResult("static", "ok", (), secrets=(1,))  # type: ignore[arg-type]


def test_run_outcome_copies_findings_and_stages():
    finding = _finding()
    findings = [finding]
    stages = {"static", "reader"}
    outcome = RunOutcome(uuid4(), "completed", stages, findings, "abc", 1)
    findings.clear()
    stages.add("detonation")

    assert outcome.status == "completed"
    assert outcome.content_sha256 == "abc"
    assert outcome.hash_version == 1
    assert outcome.findings == (finding,)
    assert outcome.stages_requested == frozenset({"static", "reader"})

    missing = RunOutcome(uuid4(), "error", frozenset(), (), None, 2)
    assert missing.content_sha256 is None
    assert missing.stages_requested == frozenset()
    assert missing.hash_version == 2


def test_run_outcome_accepts_every_status_and_stage():
    for status in ("completed", "timeout", "error"):
        outcome = RunOutcome(
            uuid4(),
            status,
            frozenset({"static", "reader", "detonation"}),
            (),
            None,
            2,
        )
        assert outcome.status == status
        assert outcome.stages_requested == frozenset({"static", "reader", "detonation"})


def test_run_outcome_rejects_a_bad_status_or_stage():
    with pytest.raises(ValueError):
        RunOutcome(uuid4(), "running", frozenset({"static"}), (), None, 1)
    with pytest.raises(ValueError):
        RunOutcome(uuid4(), "completed", frozenset({"intake"}), (), None, 1)


def test_run_outcome_rejects_a_non_finding():
    with pytest.raises(TypeError):
        RunOutcome(uuid4(), "completed", frozenset(), ["nope"], None, 1)  # type: ignore[list-item]


def test_approval_copies_accepted_rule_ids():
    run_id = uuid4()
    accepted = {"rule.a"}
    approval = Approval("ap-1", "abc", 2, accepted, "its job", "2026-11-05", run_id)
    accepted.add("rule.b")

    assert approval.id == "ap-1"
    assert approval.content_sha256 == "abc"
    assert approval.hash_version == 2
    assert approval.accepted == frozenset({"rule.a"})
    assert approval.reason == "its job"
    assert approval.approved_at == "2026-11-05"
    assert approval.run_id == run_id


def test_approval_rejects_a_non_rule_id():
    with pytest.raises(TypeError):
        Approval("ap-1", "abc", 2, {1}, "its job", "2026-11-05", uuid4())  # type: ignore[arg-type]


def test_new_domain_types_are_frozen(tmp_path: Path):
    entry = FileEntry("SKILL.md", 4, "text", False)
    record = SkillRecord(tmp_path, "date-helper", None, 2, (entry,))
    result = StageResult("static", "ok", ())
    outcome = RunOutcome(uuid4(), "completed", frozenset({"static"}), (), None, 2)
    approval = _approval()

    with pytest.raises(FrozenInstanceError):
        entry.size = 0  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.detail = "x"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        outcome.hash_version = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        approval.reason = "no"  # type: ignore[misc]


def _finding() -> Finding:
    return Finding(Source.SEMGREP, "semgrep.ok", Severity.INFO)


def _approval() -> Approval:
    return Approval("ap-1", "abc", 2, frozenset({"rule.a"}), "its job", "2026-11-05", uuid4())
