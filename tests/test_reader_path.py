from pathlib import Path

import pytest

from skill_warden.breaker import Breaker
from skill_warden.hashing import content_hash
from skill_warden.orchestrator import Orchestrator
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import rule_path
from skill_warden.store import Store
from tests.clickhouse import finding_rows, has_memory_persistence, latest_run_id

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[1]
RULES = rule_path()
PROSE = ROOT / "fixtures" / "skills" / "prose-exfil"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"


class ScriptedReader:
    def __init__(self, body: dict) -> None:
        self._body = body

    def call(self, _text: str) -> dict:
        return self._body


def _record(path: Path, name: str) -> SkillRecord:
    return SkillRecord(
        publisher="example",
        name=name,
        version="1.0.0",
        path=path,
        content_hash=content_hash(path),
    )


def _orchestrator(scanner, tmp_path: Path, reader: ScriptedReader) -> tuple[Orchestrator, Store]:
    store = Store(scanner)
    breaker = Breaker(
        max_usd=5.0,
        max_jobs=1,
        max_seconds=60,
        kill_path=tmp_path / "KILL",
    )
    return Orchestrator(store, breaker, RULES, reader), store


def test_prose_exfil_reader_high_is_block(scanner, tmp_path: Path):
    reader = ScriptedReader({"flags": ["credential_exfil"], "evidence": ["api keys"]})
    record = _record(PROSE, "prose-exfil")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("BLOCK", "high_finding")
    rows = finding_rows(scanner, run_id)
    assert ("credential_exfil", "high") in rows
    assert ("semgrep.ok", "info") in rows
    assert not has_memory_persistence(rows)


def test_clean_date_false_safety_claim_is_ask(scanner, tmp_path: Path):
    reader = ScriptedReader({"flags": ["false_safety_claim"], "evidence": ["safe"]})
    record = _record(CLEAN, "clean-date")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("ASK", "medium_only")


def test_reader_decision_key_is_reader_error(scanner, tmp_path: Path):
    reader = ScriptedReader({"decision": "ALLOW", "flags": []})
    record = _record(CLEAN, "clean-date")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("BLOCK", "reader_error")
