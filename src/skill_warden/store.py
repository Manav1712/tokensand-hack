from datetime import UTC, datetime
from uuid import UUID

from skill_warden.errors import RedactionError
from skill_warden.redact import contains_secret
from skill_warden.verdict import load_sql

_INSERT_SETTINGS = {"async_insert": 1, "wait_for_async_insert": 1}


class Store:
    def __init__(self, client, secrets: list[str] | None = None) -> None:
        self._client = client
        self._secrets = [] if secrets is None else secrets

    def insert_run(
        self,
        run_id: UUID,
        skill_hash: str,
        *,
        backend: str = "local",
        budget_cents: int = 0,
    ) -> None:
        self._client.insert(
            "scan_runs",
            [[
                run_id,
                skill_hash,
                datetime.now(UTC),
                None,
                backend,
                "running",
                budget_cents,
            ]],
            column_names=[
                "run_id",
                "skill_hash",
                "started_at",
                "finished_at",
                "backend",
                "status",
                "budget_cents",
            ],
            settings=_INSERT_SETTINGS,
        )

    def insert_findings(self, run_id: UUID, rows: list[dict[str, str]]) -> None:
        if any(contains_secret(row["excerpt"], self._secrets) for row in rows):
            raise RedactionError("excerpt contains a configured secret")
        self._client.insert(
            "findings",
            [
                [
                    run_id,
                    row["source"],
                    row["rule_id"],
                    row["severity"],
                    row["file"],
                    row["evidence_hash"],
                    row["excerpt"],
                ]
                for row in rows
            ],
            column_names=[
                "run_id",
                "source",
                "rule_id",
                "severity",
                "file",
                "evidence_hash",
                "excerpt",
            ],
            settings=_INSERT_SETTINGS,
        )

    def finish_run(self, run_id: UUID, status: str) -> None:
        self._client.command(
            """
            ALTER TABLE skill_warden.scan_runs
            UPDATE status = {status:String}, finished_at = now64(3, 'UTC')
            WHERE run_id = {run_id:UUID}
            """,
            parameters={"status": status, "run_id": str(run_id)},
            settings={"mutations_sync": 1},
        )

    def verdict(self, run_id: UUID) -> tuple[str, str]:
        result = self._client.query(
            load_sql().strip().rstrip(";"),
            parameters={"run_id": str(run_id)},
        )
        row = dict(zip(result.column_names, result.result_rows[0], strict=True))
        return str(row["decision"]), str(row["reason_code"])
