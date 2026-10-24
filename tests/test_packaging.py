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

_SCAN = """\
import json
from pathlib import Path
from skill_warden.semgrep import rule_path, scan
report = scan([Path("SKILL.md")], rule_path())
print(json.dumps(report))
"""


def test_installed_wheel_scan_finds_memory_rule(tmp_path: Path):
    wheel_dir = tmp_path / "wheels"
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

    venv = tmp_path / "venv"
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

    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copy(MEMORY, outside / "SKILL.md")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PATH"] = os.pathsep.join([str(venv / "bin"), env.get("PATH", "")])
    scanned = subprocess.run(
        [str(python), "-P", "-c", _SCAN],
        cwd=outside,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert scanned.returncode == 0, scanned.stderr
    report = json.loads(scanned.stdout)
    assert any(
        str(result.get("check_id", "")).endswith("skill-memory-file-persistence")
        for result in report["results"]
    )
