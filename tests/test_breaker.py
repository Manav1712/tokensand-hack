from pathlib import Path

import pytest

from skill_warden.breaker import Breaker
from skill_warden.errors import BudgetError


def _breaker(tmp_path: Path, **overrides: float) -> Breaker:
    params = {
        "max_usd": 5.0,
        "max_jobs": 1,
        "max_seconds": 60,
        "kill_path": tmp_path / "KILL",
    }
    params.update(overrides)
    return Breaker(**params)


def test_kill_file_refuses_job(tmp_path: Path):
    kill = tmp_path / "KILL"
    kill.write_text("stop")
    breaker = _breaker(tmp_path, kill_path=kill)

    with pytest.raises(BudgetError):
        breaker.enter(1.0)

    assert breaker.active == 0
    assert breaker.spent == 0.0


def test_second_job_refused_at_max_jobs(tmp_path: Path):
    breaker = _breaker(tmp_path, max_jobs=1)

    breaker.enter(1.0)
    with pytest.raises(BudgetError):
        breaker.enter(1.0)

    assert breaker.active == 1
    assert breaker.spent == 1.0


def test_spend_ceiling_refuses_job(tmp_path: Path):
    breaker = _breaker(tmp_path, max_usd=1.0)

    with pytest.raises(BudgetError):
        breaker.enter(2.0)

    assert breaker.active == 0
    assert breaker.spent == 0.0


def test_leave_then_enter_keeps_first_estimate(tmp_path: Path):
    breaker = _breaker(tmp_path)

    breaker.enter(1.0)
    breaker.leave()
    breaker.enter(0.0)

    assert breaker.spent == 1.0
    assert breaker.active == 1


def test_exceeded_uses_injected_clock(tmp_path: Path):
    breaker = _breaker(tmp_path, max_seconds=60)

    assert breaker.exceeded(0.0, clock=lambda: 61.0) is True
    assert breaker.exceeded(0.0, clock=lambda: 60.0) is False
