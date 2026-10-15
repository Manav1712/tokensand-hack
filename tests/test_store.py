import subprocess
import time
import uuid
from pathlib import Path

import pytest

from skill_warden.store import Store
from skill_warden.errors import RedactionError


def _ensure_container() -> None:
    info = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if info.returncode != 0:
        pytest.fail(info.stderr)

    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "skill-warden-ch-test"],
        capture_output=True,
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
            capture_output=True,
            text=True,
        )
        if started.returncode != 0:
            pytest.fail(started.stderr)
    elif inspect.stdout.strip() != "true":
        started = subprocess.run(
            ["docker", "start", "skill-warden-ch-test"],
            capture_output=True,
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
        except Exception as exc:
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


def _finding(rule_id: str, severity: str, excerpt: str = "") -> dict[str, str]:
    return {
        "source": "semgrep",
        "rule_id": rule_id,
        "severity": severity,
        "file": "",
        "evidence_hash": rule_id,
        "excerpt": excerpt,
    }


def test_completed_semgrep_ok_is_allow(scanner):
    store = Store(scanner)
    run_id = uuid.uuid4()
    store.insert_run(run_id, "hash")
    store.insert_findings(run_id, [_finding("semgrep.ok", "info")])
    store.finish_run(run_id, "completed")

    assert store.verdict(run_id) == ("ALLOW", "clean")


def test_high_finding_is_block(scanner):
    store = Store(scanner)
    run_id = uuid.uuid4()
    store.insert_run(run_id, "hash")
    store.insert_findings(run_id, [_finding("rule.high", "high")])
    store.finish_run(run_id, "completed")

    assert store.verdict(run_id) == ("BLOCK", "high_finding")


def test_unredacted_excerpt_is_refused(scanner):
    store = Store(scanner, secrets=["FAKE-CANARY-TOKEN"])
    run_id = uuid.uuid4()
    row = _finding("rule.high", "high", "token FAKE-CANARY-TOKEN here")

    with pytest.raises(RedactionError):
        store.insert_findings(run_id, [row])

    result = scanner.query(
        "SELECT count() FROM skill_warden.findings WHERE run_id = {run_id:UUID}",
        parameters={"run_id": str(run_id)},
    )
    assert result.result_rows[0][0] == 0
