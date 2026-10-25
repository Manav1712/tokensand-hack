import hashlib
import uuid
from pathlib import Path

import pytest

from skill_warden.errors import RedactionError
from skill_warden.hashing import content_hash
from skill_warden.jail import detonate
from skill_warden.memory_store import MemoryStore
from skill_warden.models import Report, Severity, Source, Verdict
from skill_warden.pipeline import scan, scan_skill
from skill_warden.reader import ReaderResult
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import rule_path, scan as semgrep_scan

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


def _row(source: str, rule_id: str, severity: str, excerpt: str = "") -> dict[str, str]:
    return {
        "source": source,
        "rule_id": rule_id,
        "severity": severity,
        "file": "",
        "excerpt": excerpt,
        "evidence_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
    }


_OK = _row("semgrep", "semgrep.ok", "info")


def _record(path: Path, name: str) -> SkillRecord:
    return SkillRecord(
        publisher="example",
        name=name,
        version="1.0.0",
        path=path,
        content_hash=content_hash(path),
    )


def test_memory_poison_is_block(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []
    real = content_hash

    def spy(path: Path) -> str:
        seen.append(Path(path))
        return real(path)

    monkeypatch.setattr("skill_warden.pipeline.content_hash", spy)

    report = scan_skill(MEMORY)

    assert seen == [MEMORY]
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
    assert [finding.rule_id for finding in report.findings] == ["semgrep.ok"]


def test_detonate_false_does_not_call_jail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skill_warden.pipeline.jail_detonate", _boom)
    monkeypatch.setattr("skill_warden.jail.detonate", _boom)

    report = scan_skill(CLEAN, detonate=False)

    assert report.verdict == Verdict("ALLOW", "clean", "")


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
        monkeypatch.setattr("skill_warden.pipeline.content_hash", _boom)
    elif stage == "semgrep.scan":
        monkeypatch.setattr("skill_warden.pipeline.semgrep_scan", _boom)
    elif stage == "llm.call":
        llm = _Boom()
    elif stage == "policy.decide":
        monkeypatch.setattr("skill_warden.pipeline.decide", _boom)
    else:
        monkeypatch.setattr("skill_warden.pipeline.jail_detonate", _boom)
        detonate_skill = True

    report = scan_skill(CLEAN, llm=llm, detonate=detonate_skill)

    assert report == Report((), _BLOCKED)
    assert report.verdict.detail == ""


def test_scan_continues_after_one_skill_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("do nothing\n", encoding="utf-8")
    calls = {"n": 0}
    real = semgrep_scan

    def flaky(paths: list[Path], config: Path) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("semgrep failed")
        return real(paths, config)

    monkeypatch.setattr("skill_warden.pipeline.semgrep_scan", flaky)

    reports = scan([broken, CLEAN])

    assert calls["n"] == 2
    assert isinstance(reports, tuple)
    assert reports[0] == Report((), _BLOCKED)
    assert reports[1].verdict == Verdict("ALLOW", "clean", "")


@pytest.mark.parametrize(
    ("rows", "status", "expected"),
    [
        ([_OK], "completed", ("ALLOW", "clean")),
        ([_OK, _row("semgrep", "rule.high", "high")], "completed", ("BLOCK", "high_finding")),
        ([_row("canary", "honeytoken", "critical")], "completed", ("BLOCK", "canary")),
        (
            [_row("reader", "reader_invalid", "error"), _OK],
            "completed",
            ("BLOCK", "reader_error"),
        ),
        ([_row("policy", "ruleset_empty", "error")], "completed", ("BLOCK", "tool_error")),
        ([_row("semgrep", "rule.medium", "medium")], "completed", ("ASK", "medium_only")),
        ([], "completed", ("BLOCK", "no_findings")),
        ([_row("reader", "note", "low")], "completed", ("BLOCK", "semgrep_missing")),
        ([_OK], "timeout", ("BLOCK", "timeout")),
    ],
)
def test_memory_store_verdict_uses_policy(
    rows: list[dict[str, str]],
    status: str,
    expected: tuple[str, str],
) -> None:
    store = MemoryStore()
    run_id = uuid.uuid4()

    store.insert_run(run_id, "hash", backend="local", budget_cents=0)
    store.insert_findings(run_id, rows)
    store.finish_run(run_id, status)

    assert store.verdict(run_id) == expected


def test_unfinished_and_unknown_runs_are_not_finished() -> None:
    store = MemoryStore()
    run_id = uuid.uuid4()
    store.insert_run(run_id, "hash")
    store.insert_findings(run_id, [_OK])

    assert store.verdict(run_id) == ("BLOCK", "not_finished")
    assert store.verdict(uuid.uuid4()) == ("BLOCK", "not_finished")


def test_memory_store_rejects_secret_excerpts_and_keeps_runs_apart() -> None:
    store = MemoryStore(secrets=["abcd", "abc"])
    leaked = uuid.uuid4()
    store.insert_run(leaked, "hash")
    with pytest.raises(RedactionError, match="excerpt contains a configured secret"):
        store.insert_findings(leaked, [_row("semgrep", "semgrep.ok", "info", excerpt="token abcd")])
    store.finish_run(leaked, "completed")

    short = uuid.uuid4()
    store.insert_run(short, "hash", backend="local", budget_cents=1)
    store.insert_findings(short, [_row("semgrep", "semgrep.ok", "info", excerpt="abc")])
    store.finish_run(short, "completed")

    blocked = uuid.uuid4()
    store.insert_run(blocked, "other")
    store.insert_findings(blocked, [_OK, _row("semgrep", "rule.high", "high")])
    store.finish_run(blocked, "completed")

    assert store.verdict(short) == ("ALLOW", "clean")
    assert store.verdict(blocked) == ("BLOCK", "high_finding")
    assert store.verdict(leaked) == ("BLOCK", "no_findings")


class _SpyStore(MemoryStore):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__(secrets=secrets)
        self.batches: list[list[dict[str, str]]] = []

    def insert_findings(self, run_id: uuid.UUID, rows: list[dict[str, str]]) -> None:
        self.batches.append(list(rows))
        super().insert_findings(run_id, rows)


def _justifies_block(rows: list[dict[str, str]]) -> bool:
    return any(
        row["source"] == "canary" or row["severity"] in {"high", "critical"}
        for row in rows
    )


@pytest.mark.docker
def test_detonate_without_clickhouse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_client(*_args: object, **_kwargs: object) -> None:
        pytest.fail("clickhouse")

    monkeypatch.setattr("clickhouse_connect.get_client", fail_client)

    reports = scan([STEAL, CLEAN], detonate=True)

    assert reports[0].verdict.decision == "BLOCK"
    assert reports[0].verdict.reason in {"canary", "high_finding"}
    assert _justifies_block([finding.to_row() for finding in reports[0].findings])
    assert reports[1].verdict == Verdict("ALLOW", "clean", "")

    nonce = "FAKE-CANARY-NONCE"
    expectations = (
        (STEAL, "steal-key", "BLOCK", {"canary", "high_finding"}),
        (CLEAN, "clean-date", "ALLOW", {"clean"}),
    )
    for path, name, decision, reasons in expectations:
        scratch = tmp_path / name
        scratch.mkdir()
        store = _SpyStore([nonce])
        run_id = uuid.uuid4()
        result = detonate(
            _record(path, name),
            store,
            run_id=run_id,
            nonce=nonce,
            rules=rule_path(),
            scratch=scratch,
        )

        assert result[0] == decision
        assert result[1] in reasons
        assert store.verdict(run_id) == result
        if decision == "BLOCK":
            assert _justifies_block(store.batches[0])
