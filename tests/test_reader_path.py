import subprocess
import time
from pathlib import Path

import pytest

from skill_warden.breaker import Breaker
from skill_warden.hashing import content_hash
from skill_warden.orchestrator import Orchestrator
from skill_warden.registry import SkillRecord
from skill_warden.store import Store

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "memory.yaml"
PROSE = ROOT / "fixtures" / "skills" / "prose-exfil"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"


def _ensure_container() -> None:
    info = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
    if info.returncode != 0:
        pytest.fail(info.stderr)

    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "skill-warden-ch-test"],
        check=False, capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        if "No such" not in inspect.stderr:
            pytest.fail(inspect.stderr)
        started = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "skill-warden-ch-test",
                "--ulimit",
                "nofile=262144:262144",
                "-p",
                "18123:8123",
                "-e",
                "CLICKHOUSE_DB=skill_warden",
                "-e",
                "CLICKHOUSE_USER=admin",
                "-e",
                "CLICKHOUSE_PASSWORD=test",
                "-e",
                "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1",
                "clickhouse/clickhouse-server:26.9",
            ],
            check=False, capture_output=True,
            text=True,
        )
        if started.returncode != 0:
            pytest.fail(started.stderr)
    elif inspect.stdout.strip() != "true":
        started = subprocess.run(
            ["docker", "start", "skill-warden-ch-test"],
            check=False, capture_output=True,
            text=True,
        )
        if started.returncode != 0:
            pytest.fail(started.stderr)


def _admin_client(clickhouse_connect):
    deadline = time.monotonic() + 60
    last_error = "SELECT 1 did not succeed"
    while time.monotonic() < deadline:
        try:
            admin = clickhouse_connect.get_client(
                host="localhost",
                port=18123,
                username="admin",
                password="test",
                database="skill_warden",
                secure=False,
            )
            admin.query("SELECT 1")
            return admin
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(1)
    pytest.fail(last_error)


def _apply_schema(admin) -> None:
    from clickhouse_connect.driver.exceptions import DatabaseError

    schema_path = Path(__file__).resolve().parents[1] / "schema" / "001_init.sql"
    if not schema_path.is_file():
        pytest.fail(f"missing schema file: {schema_path}")

    for statement in schema_path.read_text(encoding="utf-8").split(";"):
        piece = statement.strip()
        if not piece:
            continue
        try:
            admin.command(piece)
        except DatabaseError as exc:
            if "TABLE_ALREADY_EXISTS" not in str(exc):
                raise


@pytest.fixture(scope="session")
def scanner():
    _ensure_container()
    import clickhouse_connect

    admin = _admin_client(clickhouse_connect)
    _apply_schema(admin)
    client = clickhouse_connect.get_client(
        host="localhost",
        port=18123,
        username="scanner",
        password="test",
        database="skill_warden",
        secure=False,
    )
    yield client


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


def _latest_run_id(scanner, skill_hash: str):
    result = scanner.query(
        """
        SELECT run_id
        FROM skill_warden.scan_runs
        WHERE skill_hash = {skill_hash:String}
        ORDER BY started_at DESC
        LIMIT 1
        """,
        parameters={"skill_hash": skill_hash},
    )
    return result.result_rows[0][0]


def _findings(scanner, run_id) -> list[tuple]:
    result = scanner.query(
        """
        SELECT rule_id, severity
        FROM skill_warden.findings
        WHERE run_id = {run_id:UUID}
        """,
        parameters={"run_id": str(run_id)},
    )
    return result.result_rows


def _has_persistence(rows: list[tuple]) -> bool:
    return any(
        str(rule_id).endswith("skill-memory-file-persistence") and severity == "high"
        for rule_id, severity in rows
    )


def test_prose_exfil_reader_high_is_block(scanner, tmp_path: Path):
    reader = ScriptedReader({"flags": ["credential_exfil"], "evidence": ["api keys"]})
    record = _record(PROSE, "prose-exfil")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = _latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("BLOCK", "high_finding")
    rows = _findings(scanner, run_id)
    assert ("credential_exfil", "high") in rows
    assert ("semgrep.ok", "info") in rows
    assert not _has_persistence(rows)


def test_clean_date_false_safety_claim_is_ask(scanner, tmp_path: Path):
    reader = ScriptedReader({"flags": ["false_safety_claim"], "evidence": ["safe"]})
    record = _record(CLEAN, "clean-date")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = _latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("ASK", "medium_only")


def test_reader_decision_key_is_reader_error(scanner, tmp_path: Path):
    reader = ScriptedReader({"decision": "ALLOW", "flags": []})
    record = _record(CLEAN, "clean-date")
    orchestrator, store = _orchestrator(scanner, tmp_path, reader)

    decision = orchestrator.run(record)

    run_id = _latest_run_id(scanner, record.content_hash)
    assert decision == store.verdict(run_id)[0]
    assert store.verdict(run_id) == ("BLOCK", "reader_error")
