import os
from collections.abc import Callable
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


@pytest.fixture
def fake_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[str, str], Path]:
    def factory(name: str, script: str) -> Path:
        directory = tmp_path / "fake-bin"
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
        monkeypatch.setenv(
            "PATH",
            os.pathsep.join([str(directory), os.environ.get("PATH", "")]),
        )
        return path

    return factory
