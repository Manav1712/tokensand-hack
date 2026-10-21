from __future__ import annotations

import json
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from skill_warden.errors import SinkError

NETWORK_NAME = "jailnet"
SUBNET = "172.30.15.0/24"
GATEWAY = "172.30.15.1"
SINK_IP = "172.30.15.2"
IMAGE_TAG = "skill-warden-sink:step17"
HTTP_LOG_PATH = "/var/log/skill-warden-http.log"
PROBE_IMAGE = "busybox:1.36.1"
LABEL_KEY = "skill-warden.component"
LABEL_VAL = "sink"
SINK_CONTAINER_NAME = "skill-warden-sink"
_cached_http_log: str = ""

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SINK_BUILD_CONTEXT = _REPO_ROOT / "docker" / "sink"


@dataclass
class ProbeResult:
    stdout: str
    stderr: str
    exit_code: int
    dns_servers: list[str]
    mount_sources: list[str]
    port_bindings: dict


@dataclass
class Session:
    network_name: str
    sink_container_id: str
    _stopped: bool = field(default=False, repr=False)


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SinkError(result.stderr.strip() or " ".join(args))
    return result


def _docker_info_ok() -> None:
    info = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
    if info.returncode != 0:
        raise SinkError(info.stderr.strip() or "docker info failed")


def _network_inspect() -> dict | None:
    result = subprocess.run(
        ["docker", "network", "inspect", NETWORK_NAME],
        check=False, capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)[0]


def _cleanup_labeled() -> None:
    listed = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label={LABEL_KEY}={LABEL_VAL}",
        ],
        check=False, capture_output=True,
        text=True,
    )
    ids = [line for line in listed.stdout.splitlines() if line.strip()]
    if ids:
        subprocess.run(["docker", "rm", "-f", *ids], check=False, capture_output=True, text=True)
    net = _network_inspect()
    if net is not None:
        labels = net.get("Labels") or {}
        if labels.get(LABEL_KEY) == LABEL_VAL:
            subprocess.run(
                ["docker", "network", "rm", NETWORK_NAME],
                check=False, capture_output=True,
                text=True,
            )


def _ensure_network() -> None:
    existing = _network_inspect()
    if existing is not None:
        labels = existing.get("Labels") or {}
        if labels.get(LABEL_KEY) != LABEL_VAL:
            raise SinkError(
                f"network {NETWORK_NAME} exists without {LABEL_KEY}={LABEL_VAL}"
            )
        _cleanup_labeled()
    create = subprocess.run(
        [
            "docker",
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--ipv6=false",
            "--subnet",
            SUBNET,
            "--gateway",
            GATEWAY,
            "--opt",
            "com.docker.network.bridge.gateway_mode_ipv4=isolated",
            "--label",
            f"{LABEL_KEY}={LABEL_VAL}",
            NETWORK_NAME,
        ],
        check=False, capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        raise SinkError(create.stderr.strip() or "docker network create failed")


def build_image() -> None:
    _docker_info_ok()
    build = subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, str(_SINK_BUILD_CONTEXT)],
        check=False, capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        raise SinkError(build.stderr.strip() or "docker build failed")
    pull = subprocess.run(
        ["docker", "pull", PROBE_IMAGE],
        check=False, capture_output=True,
        text=True,
    )
    if pull.returncode != 0:
        inspect = subprocess.run(
            ["docker", "image", "inspect", PROBE_IMAGE],
            check=False, capture_output=True,
            text=True,
        )
        if inspect.returncode != 0:
            raise SinkError(pull.stderr.strip() or f"failed to pull {PROBE_IMAGE}")


def start() -> Session:
    _docker_info_ok()
    _ensure_network()
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            SINK_CONTAINER_NAME,
            "--network",
            NETWORK_NAME,
            "--ip",
            SINK_IP,
            "--label",
            f"{LABEL_KEY}={LABEL_VAL}",
            "-e",
            f"SINK_IP={SINK_IP}",
            IMAGE_TAG,
        ],
        check=False, capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        _cleanup_labeled()
        raise SinkError(run.stderr.strip() or "docker run sink failed")
    container_id = run.stdout.strip()
    return Session(network_name=NETWORK_NAME, sink_container_id=container_id)


def stop(session: Session | None) -> None:
    if session is None or session._stopped:
        return
    _cleanup_labeled()
    session._stopped = True


def dns_log(session: Session) -> str:
    del session
    logs = subprocess.run(
        ["docker", "logs", SINK_CONTAINER_NAME],
        check=False, capture_output=True,
        text=True,
    )
    if logs.returncode != 0:
        raise SinkError(logs.stderr.strip() or "docker logs failed")
    return logs.stdout + logs.stderr


def http_log(session: Session | None = None) -> str:
    del session
    global _cached_http_log
    result = subprocess.run(
        ["docker", "exec", SINK_CONTAINER_NAME, "cat", HTTP_LOG_PATH],
        check=False, capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        _cached_http_log = result.stdout
        return result.stdout
    if _cached_http_log:
        return _cached_http_log
    raise SinkError(result.stderr.strip() or "docker exec http log failed")


def run_probe(session: Session, argv: list[str], timeout: int = 10) -> ProbeResult:
    del session
    name = f"skill-warden-probe-{uuid.uuid4().hex[:12]}"
    try:
        run = subprocess.run(
            [
                "docker",
                "run",
                "--name",
                name,
                "--network",
                NETWORK_NAME,
                "--dns",
                SINK_IP,
                "--label",
                f"{LABEL_KEY}={LABEL_VAL}",
                PROBE_IMAGE,
                *argv,
            ],
            check=False, capture_output=True,
            text=True,
            timeout=timeout,
        )
        inspect = subprocess.run(
            ["docker", "inspect", name],
            check=False, capture_output=True,
            text=True,
        )
        if inspect.returncode != 0:
            raise SinkError(inspect.stderr.strip() or "docker inspect probe failed")
        data = json.loads(inspect.stdout)[0]
        host = data["HostConfig"]
        dns_servers = list(host.get("Dns") or [])
        port_bindings = host.get("PortBindings") or {}
        mount_sources = [
            m.get("Source", "") for m in data.get("Mounts") or [] if m.get("Source")
        ]
        return ProbeResult(
            stdout=run.stdout,
            stderr=run.stderr,
            exit_code=run.returncode,
            dns_servers=dns_servers,
            mount_sources=mount_sources,
            port_bindings=port_bindings,
        )
    except subprocess.TimeoutExpired as exc:
        raise SinkError(f"probe timed out after {timeout}s") from exc
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, text=True)


@contextmanager
def session():
    sess = start()
    try:
        yield sess
    finally:
        stop(sess)
