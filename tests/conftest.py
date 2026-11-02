import os
from pathlib import Path

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=500)
settings.register_profile("nightly", max_examples=5000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture(autouse=True)
def history_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "warden-home"
    monkeypatch.setenv("SKILL_WARDEN_HOME", str(home))
    return home
