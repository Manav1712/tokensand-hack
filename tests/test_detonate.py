import subprocess
import time
import uuid
from pathlib import Path

import pytest

from skill_warden.findings import build_rows
from skill_warden.hashing import content_hash
from skill_warden.honeytoken import build_home, search_nonce
from skill_warden.jail import (
    container_argv,
    detonate,
    events_from_observation,
    phase_commands,
    plan,
)
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import rule_path
from skill_warden.sink import SINK_IP
from skill_warden.store import Store

ROOT = Path(__file__).resolve().parents[1]
RULES = rule_path()
STEAL_KEY = ROOT / "fixtures" / "skills" / "steal-key"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"
JAIL_IMAGE = "warden/jail:latest"
NONCE = "FAKE-CANARY-NONCE"
AGENT_HOME = "/home/agent"
PLANT_REL = "aws/credentials"
PLANT_ABS = f"{AGENT_HOME}/{PLANT_REL}"


def _record(path: Path, name: str) -> SkillRecord:
    return SkillRecord(
        publisher="example",
        name=name,
        version="1.0.0",
        path=path,
        content_hash=content_hash(path),
    )


def test_steal_key_fixture_script_shape():
    script = STEAL_KEY / "scripts" / "sync.sh"
    text = script.read_text(encoding="utf-8")

    assert script.is_file()
    assert "evil.example/collect" in text
    assert "curl" in text
    assert "${HOME}/aws/credentials" in text or '$HOME/aws/credentials' in text.replace(" ", "")
    assert "AKIA" not in text
    assert "ghp_" not in text
    assert NONCE not in text
    assert "docker.sock" not in text
    assert "/Users/" not in text


def test_container_argv_prefix_matches_plan():
    tar = Path("/tmp/skill.tar")
    base = plan(tar, JAIL_IMAGE, SINK_IP)
    argv = container_argv(tar, JAIL_IMAGE, SINK_IP)

    assert argv[: len(base)] == base


def test_container_argv_includes_agent_home_env():
    argv = container_argv(Path("/tmp/skill.tar"), JAIL_IMAGE, SINK_IP)
    joined = " ".join(argv)

    assert "HOME=" in joined or "--env" in argv
    assert AGENT_HOME in joined


def test_container_argv_no_host_leaks():
    home = str(Path.home())
    argv = container_argv(Path(home) / "skill.tar", JAIL_IMAGE, SINK_IP)
    joined = " ".join(argv)

    assert home not in joined
    assert "docker.sock" not in joined
    assert "-v" not in argv


def test_container_argv_dns_points_at_sink():
    argv = container_argv(Path("/tmp/skill.tar"), JAIL_IMAGE, SINK_IP)

    assert "--dns" in argv
    assert argv[argv.index("--dns") + 1] == SINK_IP


def test_phase_commands_steal_key_runs_sync_script():
    commands = phase_commands(STEAL_KEY)

    assert commands
    flat = " ".join(" ".join(part for part in cmd) for cmd in commands)
    assert "sync.sh" in flat


def test_phase_commands_steal_key_includes_help_probe():
    commands = phase_commands(STEAL_KEY)
    help_runs = [cmd for cmd in commands if "--help" in cmd]

    assert help_runs


def test_phase_commands_clean_date_has_no_script_runs():
    commands = phase_commands(CLEAN)

    assert commands == []


def test_events_from_observation_honeytoken_open_on_successful_read():
    strace = f'openat(AT_FDCWD, "{PLANT_ABS}", O_RDONLY) = 3'
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[PLANT_REL],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "honeytoken_open"} in events


def test_events_from_observation_honeytoken_open_from_open_syscall():
    strace = f'open("{PLANT_ABS}", O_RDONLY|O_LARGEFILE) = 3'
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[PLANT_REL],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "honeytoken_open"} in events


def test_events_from_observation_enoent_open_not_honeytoken():
    strace = (
        f'openat(AT_FDCWD, "{PLANT_ABS}", O_RDONLY) = -1 ENOENT (No such file or directory)'
    )
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[PLANT_REL],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert not any(event.get("kind") == "honeytoken_open" for event in events)


def test_events_from_observation_nonce_from_http_blob():
    body = f"upload={NONCE}"
    events = events_from_observation(
        strace_text="",
        diff_lines=[],
        plant_paths=[],
        blobs={"http": body},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "nonce"} in events
    assert search_nonce({"http": body}, NONCE) == ["http"]


def test_events_from_observation_connect_to_sink_allowed():
    strace = (
        f'connect(3, {{sa_family=AF_INET, sin_port=htons(80), '
        f'sin_addr=inet_addr("{SINK_IP}")}}, 16) = 0'
    )
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert not any(event.get("kind") == "connect" for event in events)


def test_events_from_observation_egress_connect():
    strace = (
        'connect(3, {sa_family=AF_INET, sin_port=htons(443), '
        'sin_addr=inet_addr("1.1.1.1")}, 16) = 0'
    )
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "connect", "dst": "1.1.1.1:443"} in events


def test_events_from_observation_persistence_from_diff():
    events = events_from_observation(
        strace_text="",
        diff_lines=["C /home/agent/.bashrc"],
        plant_paths=[],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "write", "path": "/home/agent/.bashrc"} in events


def test_events_from_observation_sandbox_probe_read():
    strace = 'openat(AT_FDCWD, "/.dockerenv", O_RDONLY) = 3'
    events = events_from_observation(
        strace_text=strace,
        diff_lines=[],
        plant_paths=[],
        blobs={},
        nonce=NONCE,
        sink=SINK_IP,
    )

    assert {"kind": "read", "path": "/.dockerenv"} in events


def test_events_from_observation_maps_nonce_to_canary_row():
    events = events_from_observation(
        strace_text="",
        diff_lines=[],
        plant_paths=[],
        blobs={"http": NONCE},
        nonce=NONCE,
        sink=SINK_IP,
    )
    rows = build_rows(jail_events=events, sink=SINK_IP, secrets=[NONCE])

    assert len(rows) == 1
    assert rows[0]["source"] == "canary"
    assert rows[0]["rule_id"] == "honeytoken"
    assert NONCE not in "".join(rows[0].values())


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

    schema_path = ROOT / "schema" / "001_init.sql"
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


def _finding_excerpts(scanner, run_id: uuid.UUID) -> list[str]:
    result = scanner.query(
        """
        SELECT excerpt
        FROM skill_warden.findings
        WHERE run_id = {run_id:UUID}
        """,
        parameters={"run_id": str(run_id)},
    )
    return [row[0] for row in result.result_rows]


@pytest.fixture(scope="module")
def _docker_sink_ready():
    from skill_warden import sink

    sink.build_image()
    yield


@pytest.mark.docker
def test_docker_detonate_steal_key_blocks(scanner, tmp_path: Path, _docker_sink_ready):
    run_id = uuid.uuid4()
    store = Store(scanner, secrets=[NONCE])
    record = _record(STEAL_KEY, "steal-key")

    decision, reason = detonate(
        record,
        store,
        run_id=run_id,
        nonce=NONCE,
        rules=RULES,
        scratch=tmp_path,
    )

    assert decision == "BLOCK"
    assert reason in ("canary", "high_finding")
    assert store.verdict(run_id) == (decision, reason)


@pytest.mark.docker
def test_docker_detonate_clean_date_allow(scanner, tmp_path: Path, _docker_sink_ready):
    run_id = uuid.uuid4()
    store = Store(scanner, secrets=[NONCE])
    record = _record(CLEAN, "clean-date")

    decision, reason = detonate(
        record,
        store,
        run_id=run_id,
        nonce=NONCE,
        rules=RULES,
        scratch=tmp_path,
    )

    assert decision == "ALLOW"
    assert reason == "clean"
    assert store.verdict(run_id) == ("ALLOW", "clean")


@pytest.mark.docker
def test_docker_detonate_nonce_absent_from_clickhouse_excerpts(
    scanner, tmp_path: Path, _docker_sink_ready
):
    run_id = uuid.uuid4()
    store = Store(scanner, secrets=[NONCE])
    record = _record(STEAL_KEY, "steal-key")

    detonate(
        record,
        store,
        run_id=run_id,
        nonce=NONCE,
        rules=RULES,
        scratch=tmp_path,
    )

    for excerpt in _finding_excerpts(scanner, run_id):
        assert NONCE not in excerpt


@pytest.mark.docker
def test_docker_steal_key_http_log_records_post_body(
    scanner, tmp_path: Path, _docker_sink_ready
):
    from skill_warden import sink

    run_id = uuid.uuid4()
    store = Store(scanner, secrets=[NONCE])
    record = _record(STEAL_KEY, "steal-key")
    home = tmp_path / "home"
    build_home(home, NONCE)
    expected_fragment = (home / "aws" / "credentials").read_text(encoding="utf-8").splitlines()[1]

    detonate(
        record,
        store,
        run_id=run_id,
        nonce=NONCE,
        rules=RULES,
        scratch=tmp_path,
    )

    log = sink.http_log()

    assert "collect" in log
    assert expected_fragment.split("=")[0].strip() in log
