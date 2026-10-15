from pathlib import Path

import pytest

from skill_warden.breaker import Breaker
from skill_warden.orchestrator import Orchestrator
from skill_warden.registry import SkillRecord

_SECRETS = (
    "GITHUB_TOKEN",
    "CLICKHOUSE_PASSWORD",
    "MINISIGN_KEY",
    "AKASHML_API_KEY",
)


def _scan(_files, _rules) -> dict:
    return {"results": []}


class FakeStore:
    def __init__(self, decision: str = "ALLOW", *, fail_insert: bool = False) -> None:
        self.decision = decision
        self.fail_insert = fail_insert
        self.findings: list[list[dict[str, str]]] = []
        self.finished: list[str] = []
        self.verdict_calls = 0

    def insert_run(self, _run_id, _skill_hash) -> None:
        return None

    def insert_findings(self, _run_id, rows: list[dict[str, str]]) -> None:
        if self.fail_insert:
            raise RuntimeError("insert failed")
        self.findings.append(rows)

    def finish_run(self, _run_id, status: str) -> None:
        self.finished.append(status)

    def verdict(self, _run_id) -> tuple[str, str]:
        self.verdict_calls += 1
        return self.decision, "store"


class FakeReader:
    def __init__(self) -> None:
        self.calls = 0

    def call(self, _text: str) -> dict:
        self.calls += 1
        return {"flags": [], "evidence": []}


class FakeRunner:
    def __init__(self, events: list[dict] | None = None, *, timed_out: bool = False) -> None:
        self.events = [] if events is None else events
        self.timed_out = timed_out
        self.envs: list[dict[str, str]] = []

    def __call__(self, _record: SkillRecord, env: dict[str, str]) -> tuple[list[dict], bool]:
        self.envs.append(dict(env))
        return self.events, self.timed_out


def _record(tmp_path: Path) -> SkillRecord:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("name: demo\n", encoding="utf-8")
    return SkillRecord(
        publisher="example",
        name="demo",
        version="1.0.0",
        path=skill,
        content_hash="abc",
    )


def _breaker(tmp_path: Path) -> Breaker:
    return Breaker(max_usd=5.0, max_jobs=1, max_seconds=60, kill_path=tmp_path / "KILL")


def _orchestrator(tmp_path: Path, store: FakeStore, reader: FakeReader, runner: FakeRunner) -> Orchestrator:
    return Orchestrator(
        store,
        _breaker(tmp_path),
        tmp_path / "rules.yaml",
        reader,
        scan=_scan,
        runner=runner,
    )


def test_runner_nonce_is_inserted_as_honeytoken(tmp_path: Path):
    store = FakeStore()
    runner = FakeRunner([{"kind": "nonce"}])
    orchestrator = _orchestrator(tmp_path, store, FakeReader(), runner)

    orchestrator.run(_record(tmp_path))

    assert any(row["source"] == "canary" and row["rule_id"] == "honeytoken" for row in store.findings[0])


def test_timeout_does_not_call_reader(tmp_path: Path):
    reader = FakeReader()
    orchestrator = _orchestrator(tmp_path, FakeStore(), reader, FakeRunner(timed_out=True))

    orchestrator.run(_record(tmp_path))

    assert reader.calls == 0


def test_timeout_finishes_timeout(tmp_path: Path):
    store = FakeStore()
    orchestrator = _orchestrator(tmp_path, store, FakeReader(), FakeRunner(timed_out=True))

    orchestrator.run(_record(tmp_path))

    assert store.finished == ["timeout"]


def test_timeout_returns_store_verdict(tmp_path: Path):
    store = FakeStore("ALLOW")
    orchestrator = _orchestrator(tmp_path, store, FakeReader(), FakeRunner(timed_out=True))

    decision = orchestrator.run(_record(tmp_path))

    assert decision == "ALLOW"
    assert store.verdict_calls == 1


def test_verdict_called_once(tmp_path: Path):
    store = FakeStore("ALLOW")
    orchestrator = _orchestrator(tmp_path, store, FakeReader(), FakeRunner())

    orchestrator.run(_record(tmp_path))

    assert store.verdict_calls == 1


def test_completed_jail_run_calls_reader(tmp_path: Path):
    reader = FakeReader()
    orchestrator = _orchestrator(tmp_path, FakeStore(), reader, FakeRunner())

    orchestrator.run(_record(tmp_path))

    assert reader.calls == 1


def test_jail_env_omits_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for name in _SECRETS:
        monkeypatch.setenv(name, "EXAMPLE_TOKEN")
    monkeypatch.setenv("SKILL_WARDEN_PROBE", "kept")
    runner = FakeRunner()
    orchestrator = _orchestrator(tmp_path, FakeStore(), FakeReader(), runner)

    orchestrator.run(_record(tmp_path))

    env = runner.envs[0]
    assert env["SKILL_WARDEN_PROBE"] == "kept"
    for name in _SECRETS:
        assert name not in env


def test_insert_findings_error_still_leaves(tmp_path: Path):
    store = FakeStore(fail_insert=True)
    breaker = _breaker(tmp_path)
    orchestrator = Orchestrator(
        store,
        breaker,
        tmp_path / "rules.yaml",
        FakeReader(),
        scan=_scan,
        runner=FakeRunner([{"kind": "nonce"}]),
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        orchestrator.run(_record(tmp_path))

    assert breaker.active == 0
    assert store.verdict_calls == 0
