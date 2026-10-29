import os
from pathlib import Path
from uuid import uuid4

from skill_warden.errors import ReaderInvalid
from skill_warden.findings import build_rows
from skill_warden.hashing import skill_files
from skill_warden.reader import ReaderResult
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import scan as semgrep_scan

_JAIL_SECRET_KEYS = frozenset({
    "GITHUB_TOKEN",
    "CLICKHOUSE_PASSWORD",
    "MINISIGN_KEY",
    "AKASHML_API_KEY",
})


def _jail_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _JAIL_SECRET_KEYS}


class Orchestrator:
    def __init__(self, store, breaker, rules: Path, reader, scan=semgrep_scan, runner=None) -> None:
        self._store = store
        self._breaker = breaker
        self._rules = rules
        self._reader = reader
        self._scan = scan
        self._runner = runner

    def _reader_body(self, record: SkillRecord) -> dict | object:
        parts: list[str] = []
        for path in skill_files(record.path):
            parts.append(path.read_text(encoding="utf-8"))
        text = "\n".join(parts)
        try:
            result = self._reader.call(text)
        except ReaderInvalid:
            return {}
        if isinstance(result, ReaderResult):
            return {"flags": result.flags, "evidence": result.evidence}
        return result

    def _run_jail(self, record: SkillRecord) -> str:
        report = self._scan(skill_files(record.path), self._rules)
        self._breaker.enter(0.0)
        try:
            events, timed_out = self._runner(record, _jail_env())
            reader_body = None if timed_out else self._reader_body(record)
            rows = build_rows(semgrep=report, reader=reader_body, jail_events=events)
            run_id = uuid4()
            self._store.insert_run(run_id, record.content_hash)
            self._store.insert_findings(run_id, rows)
            self._store.finish_run(run_id, "timeout" if timed_out else "completed")
            decision, _reason = self._store.verdict(run_id)
            return decision
        finally:
            self._breaker.leave()

    def run(self, record: SkillRecord) -> str:
        if self._runner is not None:
            return self._run_jail(record)
        report = self._scan(skill_files(record.path), self._rules)
        reader_body = self._reader_body(record)
        rows = build_rows(semgrep=report, reader=reader_body)
        self._breaker.enter(0.0)
        try:
            run_id = uuid4()
            self._store.insert_run(run_id, record.content_hash)
            self._store.insert_findings(run_id, rows)
            self._store.finish_run(run_id, "completed")
            decision, _reason = self._store.verdict(run_id)
            return decision
        finally:
            self._breaker.leave()
