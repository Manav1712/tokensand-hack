"""Detonation through the console script, not the pipeline function."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.docker

ROOT = Path(__file__).resolve().parents[1]
STEAL = ROOT / "fixtures" / "skills" / "steal-key"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"


def _scan(skill: Path, home: Path) -> subprocess.CompletedProcess[str]:
    cli = Path(sys.executable).with_name("skill-warden")
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(cli.parent), env.get("PATH", "")])
    env["SKILL_WARDEN_HOME"] = str(home)
    return subprocess.run(
        [
            str(cli),
            "scan",
            str(skill),
            "--detonate",
            "--format",
            "json",
            "--no-history",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_detonate_steal_key_blocks_and_clean_date_allows(tmp_path: Path) -> None:
    steal = _scan(STEAL, tmp_path / "steal-home")
    assert steal.returncode == 20, steal.stderr
    steal_body = json.loads(steal.stdout)
    assert steal_body["reports"][0]["verdict"]["decision"] == "BLOCK"
    assert steal_body["reports"][0]["verdict"]["reason"] in {"canary", "high_finding"}

    clean = _scan(CLEAN, tmp_path / "clean-home")
    assert clean.returncode == 0, clean.stderr
    clean_body = json.loads(clean.stdout)
    assert clean_body["summary"]["worst"] == "ALLOW"
    assert clean_body["reports"][0]["verdict"] == {
        "decision": "ALLOW",
        "reason": "clean",
        "detail": "",
    }
