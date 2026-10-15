import time
from collections.abc import Callable
from pathlib import Path

from skill_warden.errors import BudgetError


class Breaker:
    def __init__(self, max_usd: float, max_jobs: int, max_seconds: float, kill_path: Path) -> None:
        self.max_usd = max_usd
        self.max_jobs = max_jobs
        self.max_seconds = max_seconds
        self.kill_path = kill_path
        self.spent = 0.0
        self.active = 0

    def enter(self, est_usd: float) -> float:
        if self.kill_path.exists():
            raise BudgetError("kill switch")
        if self.active >= self.max_jobs:
            raise BudgetError("budget")
        if self.spent + est_usd > self.max_usd:
            raise BudgetError("budget")
        self.active += 1
        self.spent += est_usd
        return time.monotonic()

    def leave(self) -> None:
        self.active -= 1

    def exceeded(
        self,
        started_monotonic: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> bool:
        return clock() - started_monotonic > self.max_seconds
