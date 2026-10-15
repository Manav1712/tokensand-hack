WITH
    runs AS (
        SELECT
            count() AS run_count,
            any(status) AS run_status,
            any(finished_at) AS finished_at,
            any(inserted_at) AS inserted_at
        FROM skill_warden.scan_runs
        WHERE run_id = {run_id:UUID}
    ),
    f AS (
        SELECT
            count() AS finding_rows,
            countIf(source = 'semgrep') AS semgrep_rows,
            countIf(source = 'canary') AS canary_rows,
            countIf(source = 'reader' AND severity = 'error') AS reader_error_rows,
            countIf(severity = 'error' AND source != 'reader') AS other_error_rows,
            countIf(severity IN ('high', 'critical')) AS high_rows,
            countIf(severity = 'medium') AS medium_rows
        FROM skill_warden.findings
        WHERE run_id = {run_id:UUID}
    )
SELECT
    {run_id:UUID} AS run_id,
    multiIf(
        run_count = 0, 'BLOCK',
        run_count != 1, 'BLOCK',
        run_status = 'timeout', 'BLOCK',
        run_status = 'running' AND inserted_at < now64(3, 'UTC') - INTERVAL 10 MINUTE, 'BLOCK',
        run_status != 'completed' OR finished_at IS NULL, 'BLOCK',
        finding_rows = 0, 'BLOCK',
        canary_rows > 0, 'BLOCK',
        reader_error_rows > 0, 'BLOCK',
        other_error_rows > 0, 'BLOCK',
        high_rows > 0, 'BLOCK',
        semgrep_rows = 0, 'BLOCK',
        medium_rows > 0, 'ASK',
        'ALLOW'
    ) AS decision,
    multiIf(
        run_count = 0, 'missing_run',
        run_count != 1, 'duplicate_run',
        run_status = 'timeout', 'timeout',
        run_status = 'running' AND inserted_at < now64(3, 'UTC') - INTERVAL 10 MINUTE, 'timeout',
        run_status != 'completed' OR finished_at IS NULL, 'not_finished',
        finding_rows = 0, 'no_findings',
        canary_rows > 0, 'canary',
        reader_error_rows > 0, 'reader_error',
        other_error_rows > 0, 'tool_error',
        high_rows > 0, 'high_finding',
        semgrep_rows = 0, 'semgrep_missing',
        medium_rows > 0, 'medium_only',
        'clean'
    ) AS reason_code
FROM runs
CROSS JOIN f;
