from pathlib import Path

import pytest

from skill_warden.hashing import content_hash_v2
from skill_warden.models import Report, Severity, Source, Verdict
from skill_warden.pipeline import scan, scan_skill
from skill_warden.reader import ReaderResult
from skill_warden.static.semgrep import scan as static_scan

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"
STEAL = ROOT / "fixtures" / "skills" / "steal-key"
_BLOCKED = Verdict("BLOCK", "not_finished")


class _Reader:
    def __init__(self, result: dict | ReaderResult) -> None:
        self.result = result
        self.texts: list[str] = []

    def call(self, text: str) -> dict | ReaderResult:
        self.texts.append(text)
        return self.result


class _Boom:
    def call(self, _text: str) -> dict:
        raise RuntimeError("stage failed")


def _boom(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("stage failed")


def test_memory_poison_is_block() -> None:
    report = scan_skill(MEMORY)

    assert report.skill is not None
    assert report.skill.hash_version == 2
    assert report.skill.content_sha256 == content_hash_v2(MEMORY)
    assert isinstance(report, Report)
    assert report.verdict.decision == "BLOCK"
    assert report.verdict.reason == "high_finding"
    assert report.verdict.detail.endswith("skill-memory-file-persistence")
    matched = [
        finding
        for finding in report.findings
        if finding.source == Source.SEMGREP
        and finding.severity == Severity.HIGH
        and finding.rule_id.endswith("skill-memory-file-persistence")
    ]
    assert len(matched) == 1
    assert report.verdict.detail == matched[0].rule_id


def test_clean_date_is_allow() -> None:
    report = scan_skill(CLEAN)

    assert report.verdict == Verdict("ALLOW", "clean", "")
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.source == Source.SEMGREP
    assert finding.rule_id == "semgrep.ok"
    assert finding.severity == Severity.INFO
    assert finding.file == ""
    assert finding.line is None
    assert finding.excerpt == ""


def test_reader_is_not_called_when_llm_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "skill_warden.reader.Reader.call",
        lambda *_args, **_kwargs: pytest.fail("reader called"),
    )

    report = scan_skill(CLEAN, llm=None)

    assert report.verdict == Verdict("ALLOW", "clean", "")


def test_reader_credential_exfil_blocks_clean_date() -> None:
    reader = _Reader({"flags": ["credential_exfil"], "evidence": ["sent the note"]})

    report = scan_skill(CLEAN, llm=reader)

    assert reader.texts == [(CLEAN / "SKILL.md").read_text(encoding="utf-8")]
    assert report.verdict == Verdict("BLOCK", "high_finding", "credential_exfil")


def test_reader_result_credential_exfil_blocks_clean_date() -> None:
    reader = _Reader(ReaderResult(["credential_exfil"], ["sent the note"]))

    report = scan_skill(CLEAN, llm=reader)

    assert "YYYY-MM-DD" in reader.texts[0]
    assert report.verdict == Verdict("BLOCK", "high_finding", "credential_exfil")


def test_reader_with_no_flags_stays_allow() -> None:
    reader = _Reader({"flags": [], "evidence": []})

    report = scan_skill(CLEAN, llm=reader)

    assert len(reader.texts) == 1
    assert report.verdict == Verdict("ALLOW", "clean", "")
    assert [finding.rule_id for finding in report.findings] == ["semgrep.ok", "reader.ok"]


def test_detonate_false_leaves_detonation_unrequested() -> None:
    report = scan_skill(CLEAN, detonate=False)

    assert report.verdict == Verdict("ALLOW", "clean", "")
    assert any(item.stage == "detonation" and item.status == "skipped" for item in report.coverage)


@pytest.mark.parametrize(
    "stage",
    ["content_hash", "semgrep.scan", "llm.call", "policy.decide", "jail.detonate"],
)
def test_stage_exception_is_block_not_finished(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    llm = None
    detonate_skill = False
    if stage == "content_hash":
        monkeypatch.setattr("skill_warden.pipeline.load_skill", _boom)
    elif stage == "semgrep.scan":
        monkeypatch.setattr("skill_warden.pipeline.static_scan", _boom)
    elif stage == "llm.call":
        llm = _Boom()
    elif stage == "policy.decide":
        monkeypatch.setattr("skill_warden.pipeline.decide", _boom)
    else:
        detonate_skill = True

    report = scan_skill(CLEAN, llm=llm, detonate=detonate_skill)

    if stage in {"content_hash", "policy.decide"}:
        assert report == Report((), _BLOCKED)
        assert report.verdict.detail == ""
        return
    if stage == "llm.call":
        assert report.verdict == Verdict("BLOCK", "reader_error", "reader_unavailable")
        return
    if stage == "semgrep.scan":
        assert report.verdict == Verdict("BLOCK", "tool_error", "semgrep_failed")
        return
    assert report.verdict == Verdict("BLOCK", "tool_error", "detonation_unavailable")


def test_scan_continues_after_one_skill_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("do nothing\n", encoding="utf-8")
    calls = {"n": 0}
    real = static_scan

    def flaky(*args: object, **kwargs: object):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("semgrep failed")
        return real(*args, **kwargs)

    monkeypatch.setattr("skill_warden.pipeline.static_scan", flaky)

    reports = scan([broken, CLEAN])

    assert calls["n"] == 2
    assert isinstance(reports, tuple)
    assert reports[0].verdict == Verdict("BLOCK", "tool_error", "semgrep_failed")
    assert reports[1].verdict == Verdict("ALLOW", "clean", "")

