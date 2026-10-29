"""Legacy ClickHouse walkthrough. `skill-warden scan` replaces it. Removed in M2-14."""

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import clickhouse_connect

from skill_warden.breaker import Breaker
from skill_warden.findings import build_rows
from skill_warden.registry import scan
from skill_warden.verdict import load_sql

SAMPLE = ROOT / "fixtures" / "sample"


def main() -> None:
    records = scan(SAMPLE)
    if len(records) != 1:
        raise SystemExit(f"expected one skill, found {len(records)}")
    record = records[0]
    print(f"skill: {record.publisher}/{record.name}/{record.version}")
    print(f"hash: {record.content_hash}")

    breaker = Breaker(max_usd=1.0, max_jobs=1, max_seconds=60, kill_path=SAMPLE / "KILL")
    breaker.enter(0.01)
    rows = build_rows(semgrep={"results": [], "errors": [], "paths": {"skipped": []}})
    breaker.leave()
    print(f"finding rows: {len(rows)} ({rows[0]['rule_id']}, {rows[0]['severity']})")

    run_id = str(uuid.uuid4())
    client = clickhouse_connect.get_client(
        host="localhost",
        port=18123,
        username="scanner",
        password="test",
        database="skill_warden",
        secure=False,
    )
    settings = {"async_insert": 1, "wait_for_async_insert": 1}
    client.command(
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
        )
        SELECT {run_id:UUID}, {skill_hash:String}, now64(3, 'UTC'), now64(3, 'UTC'), 'local', 'completed', 0
        """,
        parameters={"run_id": run_id, "skill_hash": record.content_hash},
        settings=settings,
    )
    row = rows[0]
    client.command(
        """
        INSERT INTO skill_warden.findings (
            run_id, source, rule_id, severity, file, evidence_hash, excerpt
        )
        SELECT {run_id:UUID}, {source:String}, {rule_id:String}, {severity:String}, '', {evidence_hash:String}, {excerpt:String}
        """,
        parameters={"run_id": run_id, **row},
        settings=settings,
    )
    result = client.query(load_sql().strip().rstrip(";"), parameters={"run_id": run_id})
    decision = dict(zip(result.column_names, result.result_rows[0], strict=True))
    print(f"decision: {decision['decision']} ({decision['reason_code']})")


if __name__ == "__main__":
    main()
