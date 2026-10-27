import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.packaging

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison" / "SKILL.md"
MEMORY_DIR = ROOT / "fixtures" / "skills" / "memory-poison"

_SCAN = """\
import json
from pathlib import Path
from skill_warden.semgrep import rule_path, scan
report = scan([Path("SKILL.md")], rule_path())
print(json.dumps(report))
"""


@pytest.fixture(scope="module")
def installed_python(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("install")
    wheel_dir = root / "wheels"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(wheel_dir),
            str(ROOT),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, wheels

    venv = root / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    python = venv / "bin" / "python"
    installed = subprocess.run(
        [str(python), "-m", "pip", "install", str(wheels[0])],
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr
    return python


def _installed_env(python: Path, home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PATH"] = os.pathsep.join([str(python.parent), env.get("PATH", "")])
    env["SKILL_WARDEN_HOME"] = str(home)
    return env


def test_installed_wheel_scan_finds_memory_rule(
    installed_python: Path,
    tmp_path: Path,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copy(MEMORY, outside / "SKILL.md")
    scanned = subprocess.run(
        [str(installed_python), "-P", "-c", _SCAN],
        cwd=outside,
        check=False,
        capture_output=True,
        text=True,
        env=_installed_env(installed_python, tmp_path / "home"),
    )
    assert scanned.returncode == 0, scanned.stderr
    report = json.loads(scanned.stdout)
    assert any(
        str(result.get("check_id", "")).endswith("skill-memory-file-persistence")
        for result in report["results"]
    )


def test_installed_cli_scans_copied_fixture(installed_python: Path, tmp_path: Path):
    outside = tmp_path / "outside"
    copied = outside / "memory-poison"
    shutil.copytree(MEMORY_DIR, copied)
    assert not copied.is_relative_to(ROOT)

    scanned = subprocess.run(
        [
            str(installed_python.parent / "skill-warden"),
            "scan",
            str(copied),
            "--format",
            "json",
            "--no-history",
        ],
        cwd=outside,
        check=False,
        capture_output=True,
        text=True,
        env=_installed_env(installed_python, tmp_path / "home"),
    )
    assert scanned.returncode == 20, scanned.stderr
    body = json.loads(scanned.stdout)
    assert body["schema"] == "skill-warden/scan@1"
    assert body["summary"]["worst"] == "BLOCK"
    assert body["reports"][0]["verdict"]["reason"] == "high_finding"
    assert _env_secrets_absent(scanned.stdout, scanned.stderr)


def _env_secrets_absent(stdout: str, stderr: str) -> bool:
    for name, value in os.environ.items():
        upper = name.upper()
        if not any(part in upper for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            continue
        if len(value) > 8 and (value in stdout or value in stderr):
            return False
    return True
