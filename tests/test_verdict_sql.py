import uuid

import pytest

from skill_warden.verdict import load_sql

pytestmark = pytest.mark.docker

_INSERT_SETTINGS = {"async_insert": 1, "wait_for_async_insert": 1}

_COMPLETED_SQL = """
INSERT INTO skill_warden.scan_runs (
    run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
)
SELECT {run_id:UUID}, 'hash', now64(3, 'UTC'), now64(3, 'UTC'), 'local', 'completed', 0
"""

_FINDING_SQL = """
INSERT INTO skill_warden.findings (
    run_id, source, rule_id, severity, file, evidence_hash, excerpt
)
SELECT {run_id:UUID}, {source:String}, {rule_id:String}, {severity:String}, '', {evidence_hash:String}, ''
"""


def _insert(scanner, run_id, sql: str, **extra: str) -> None:
    scanner.command(
        sql,
        settings=_INSERT_SETTINGS,
        parameters={"run_id": str(run_id), **extra},
    )


def _completed(scanner, run_id) -> None:
    _insert(scanner, run_id, _COMPLETED_SQL)


def _finding(
    scanner,
    run_id,
    *,
    source: str,
    rule_id: str,
    severity: str,
    evidence_hash: str,
) -> None:
    _insert(
        scanner,
        run_id,
        _FINDING_SQL,
        source=source,
        rule_id=rule_id,
        severity=severity,
        evidence_hash=evidence_hash,
    )


def _seed_missing(scanner, run_id) -> None:
    pass


def _seed_duplicate(scanner, run_id) -> None:
    _insert(
        scanner,
        run_id,
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
        )
        SELECT {run_id:UUID}, 'hash-a', now64(3, 'UTC') - INTERVAL 2 SECOND, now64(3, 'UTC'), 'local', 'completed', 0
        UNION ALL
        SELECT {run_id:UUID}, 'hash-b', now64(3, 'UTC') - INTERVAL 1 SECOND, now64(3, 'UTC'), 'local', 'completed', 0
        """,
    )
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )


def _seed_timeout(scanner, run_id) -> None:
    _insert(
        scanner,
        run_id,
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
        )
        SELECT {run_id:UUID}, 'hash', now64(3, 'UTC'), now64(3, 'UTC'), 'local', 'timeout', 0
        """,
    )


def _seed_stalled_running(scanner, run_id) -> None:
    _insert(
        scanner,
        run_id,
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents, inserted_at
        )
        SELECT
            {run_id:UUID},
            'hash',
            now64(3, 'UTC') - INTERVAL 11 MINUTE,
            NULL,
            'local',
            'running',
            0,
            now64(3, 'UTC') - INTERVAL 11 MINUTE
        """,
    )


def _seed_young_running(scanner, run_id) -> None:
    _insert(
        scanner,
        run_id,
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
        )
        SELECT {run_id:UUID}, 'hash', now64(3, 'UTC'), NULL, 'local', 'running', 0
        """,
    )
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )


def _seed_finished_at_null(scanner, run_id) -> None:
    _insert(
        scanner,
        run_id,
        """
        INSERT INTO skill_warden.scan_runs (
            run_id, skill_hash, started_at, finished_at, backend, status, budget_cents
        )
        SELECT {run_id:UUID}, 'hash', now64(3, 'UTC'), NULL, 'local', 'completed', 0
        """,
    )
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )


def _seed_no_findings(scanner, run_id) -> None:
    _completed(scanner, run_id)


def _seed_canary(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="canary",
        rule_id="canary.tripped",
        severity="critical",
        evidence_hash="e-canary",
    )


def _seed_reader_error(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="reader",
        rule_id="reader_invalid",
        severity="error",
        evidence_hash="e-reader",
    )
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )


def _seed_policy_error(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="policy",
        rule_id="ruleset_empty",
        severity="error",
        evidence_hash="e-policy",
    )


def _seed_semgrep_error(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.error",
        severity="error",
        evidence_hash="e-semgrep-error",
    )


def _seed_jail_high(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )
    _finding(
        scanner,
        run_id,
        source="jail",
        rule_id="egress",
        severity="high",
        evidence_hash="e-jail",
    )


def _seed_high(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.high",
        severity="high",
        evidence_hash="e-high",
    )


def _seed_critical(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.critical",
        severity="critical",
        evidence_hash="e-critical",
    )


def _seed_high_plus_medium(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.high",
        severity="high",
        evidence_hash="e-high",
    )
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.medium",
        severity="medium",
        evidence_hash="e-medium",
    )


def _seed_reader_medium(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="reader",
        rule_id="false_safety_claim",
        severity="medium",
        evidence_hash="e-medium",
    )


def _seed_semgrep_medium(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.medium",
        severity="medium",
        evidence_hash="e-medium",
    )


def _seed_clean_info(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="semgrep.ok",
        severity="info",
        evidence_hash="e-ok",
    )


def _seed_low_only(scanner, run_id) -> None:
    _completed(scanner, run_id)
    _finding(
        scanner,
        run_id,
        source="semgrep",
        rule_id="rule.low",
        severity="low",
        evidence_hash="e-low",
    )


@pytest.mark.parametrize(
    ("decision", "reason_code", "seed"),
    [
        pytest.param("BLOCK", "missing_run", _seed_missing, id="missing_run"),
        pytest.param("BLOCK", "duplicate_run", _seed_duplicate, id="duplicate_run"),
        pytest.param("BLOCK", "timeout", _seed_timeout, id="timeout"),
        pytest.param("BLOCK", "timeout", _seed_stalled_running, id="stalled_running"),
        pytest.param("BLOCK", "not_finished", _seed_young_running, id="young_running"),
        pytest.param("BLOCK", "not_finished", _seed_finished_at_null, id="finished_at_null"),
        pytest.param("BLOCK", "no_findings", _seed_no_findings, id="no_findings"),
        pytest.param("BLOCK", "canary", _seed_canary, id="canary"),
        pytest.param("BLOCK", "reader_error", _seed_reader_error, id="reader_error"),
        pytest.param("BLOCK", "tool_error", _seed_policy_error, id="policy_error"),
        pytest.param("BLOCK", "tool_error", _seed_semgrep_error, id="semgrep_error"),
        pytest.param("BLOCK", "high_finding", _seed_jail_high, id="jail_high"),
        pytest.param("BLOCK", "high_finding", _seed_high, id="high"),
        pytest.param("BLOCK", "high_finding", _seed_critical, id="critical"),
        pytest.param("BLOCK", "high_finding", _seed_high_plus_medium, id="high_plus_medium"),
        pytest.param("BLOCK", "semgrep_missing", _seed_reader_medium, id="reader_medium"),
        pytest.param("ASK", "medium_only", _seed_semgrep_medium, id="semgrep_medium"),
        pytest.param("ALLOW", "clean", _seed_clean_info, id="clean_info"),
        pytest.param("ALLOW", "clean", _seed_low_only, id="low_only"),
    ],
)
def test_verdict(scanner, decision, reason_code, seed):
    run_id = uuid.uuid4()
    seed(scanner, run_id)

    sql = load_sql().strip().rstrip(";")
    result = scanner.query(sql, parameters={"run_id": str(run_id)})

    assert result.row_count == 1
    row = dict(zip(result.column_names, result.result_rows[0], strict=True))
    assert row["decision"] == decision
    assert row["reason_code"] == reason_code


def test_scanner_alter_delete_access_denied(scanner):
    with pytest.raises(Exception) as caught:
        scanner.command("ALTER TABLE skill_warden.verdicts DELETE WHERE 1")

    assert "ACCESS_DENIED" in str(caught.value)
