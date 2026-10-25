from __future__ import annotations

from uuid import UUID

from skill_warden.errors import RedactionError
from skill_warden.policy import decide

_STATIC = frozenset({"static"})


class _Run:
    def __init__(self, skill_hash: str, backend: str, budget_cents: int) -> None:
        self.skill_hash = skill_hash
        self.backend = backend
        self.budget_cents = budget_cents
        self.status = "running"
        self.finished = False


class MemoryStore:
    def __init__(self, secrets: list[str] | None = None) -> None:
        self._secrets = [] if secrets is None else secrets
        self._runs: dict[UUID, _Run] = {}
        self._findings: dict[UUID, list[dict[str, str]]] = {}

    def insert_run(
        self,
        run_id: UUID,
        skill_hash: str,
        *,
        backend: str = "local",
        budget_cents: int = 0,
    ) -> None:
        self._runs[run_id] = _Run(skill_hash, backend, budget_cents)

    def insert_findings(self, run_id: UUID, rows: list[dict[str, str]]) -> None:
        if any(self._leaked(row["excerpt"]) for row in rows):
            raise RedactionError("excerpt contains a configured secret")
        self._findings.setdefault(run_id, []).extend(rows)

    def finish_run(self, run_id: UUID, status: str) -> None:
        run = self._runs[run_id]
        run.status = status
        run.finished = True

    def verdict(self, run_id: UUID) -> tuple[str, str]:
        run = self._runs.get(run_id)
        if run is None or not run.finished:
            status = "error"
        else:
            status = run.status
        verdict = decide(self._findings.get(run_id, []), _STATIC, status)
        return verdict.decision, verdict.reason

    def _leaked(self, excerpt: str) -> bool:
        return any(len(secret) > 3 and secret in excerpt for secret in self._secrets)
