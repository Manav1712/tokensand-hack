import subprocess
from pathlib import Path

import pytest

from skill_warden.observe import events_from_diff, parse_strace_log

pytestmark = pytest.mark.docker

_IMAGE = "skill-warden-observe:step16"
_DIFF_NAME = "skill-warden-observe-diff"
_STRACE_ARGV = [
    "docker",
    "run",
    "--rm",
    "--cap-drop",
    "ALL",
    _IMAGE,
    "strace",
    "-f",
    "-e",
    "trace=openat",
    "true",
]


def _require_docker() -> None:
    info = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
    if info.returncode != 0:
        pytest.fail(info.stderr)


def _container_exists(name: str) -> bool:
    inspect = subprocess.run(
        ["docker", "inspect", name],
        check=False, capture_output=True,
        text=True,
    )
    return inspect.returncode == 0


def test_strace_runs_with_cap_drop_all():
    _require_docker()
    argv = list(_STRACE_ARGV)
    cap_drop = argv.index("--cap-drop")
    assert argv[cap_drop + 1] == "ALL"
    assert "--rm" in argv
    assert "-v" not in argv
    rendered = " ".join(argv)
    assert str(Path.home()) not in rendered
    assert "docker.sock" not in rendered

    traced = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=60)
    if traced.returncode != 0:
        pytest.fail(traced.stderr)

    listed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"ancestor={_IMAGE}"],
        check=False, capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        pytest.fail(listed.stderr)
    assert listed.stdout.strip() == ""


def test_strace_openat_parses_under_cap_drop_all():
    _require_docker()
    traced = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--cap-drop",
            "ALL",
            _IMAGE,
            "strace",
            "-f",
            "-e",
            "trace=openat",
            "cat",
            "/etc/alpine-release",
        ],
        check=False, capture_output=True,
        text=True,
        timeout=60,
    )
    if traced.returncode != 0:
        pytest.fail(traced.stderr)
    assert "openat" in traced.stderr
    events = parse_strace_log(traced.stderr)
    assert any(
        event.get("syscall") == "openat" and event.get("path") == "/etc/alpine-release"
        for event in events
    )


def test_docker_diff_marks_added_path():
    _require_docker()
    created = False
    try:
        started = subprocess.run(
            [
                "docker",
                "run",
                "--name",
                _DIFF_NAME,
                "--cap-drop",
                "ALL",
                _IMAGE,
                "touch",
                "/tmp/warden-added",
            ],
            check=False, capture_output=True,
            text=True,
            timeout=60,
        )
        created = _container_exists(_DIFF_NAME)
        if started.returncode != 0:
            pytest.fail(started.stderr)

        diff = subprocess.run(
            ["docker", "diff", _DIFF_NAME],
            check=False, capture_output=True,
            text=True,
            timeout=60,
        )
        if diff.returncode != 0:
            pytest.fail(diff.stderr)
        events = events_from_diff(diff.stdout.splitlines())
        assert {"change": "added", "path": "/tmp/warden-added"} in events
    finally:
        removed = subprocess.run(
            ["docker", "rm", "-f", _DIFF_NAME],
            check=False, capture_output=True,
            text=True,
        )
        if removed.returncode != 0 and created:
            pytest.fail(removed.stderr)
