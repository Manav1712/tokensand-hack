from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def history_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "warden-home"
    monkeypatch.setenv("SKILL_WARDEN_HOME", str(home))
    return home
