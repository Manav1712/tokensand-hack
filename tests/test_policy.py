import pytest

from skill_warden.policy import decide

_STATIC = frozenset({"static"})


def _finding(source: str, rule_id: str, severity: str) -> dict[str, str]:
    return {"source": source, "rule_id": rule_id, "severity": severity}


_SEMGREP_OK = _finding("semgrep", "semgrep.ok", "info")


@pytest.mark.parametrize(
    ("findings", "stages", "status", "decision", "reason"),
    [
        pytest.param([], _STATIC, "error", "BLOCK", "not_finished", id="missing_run"),
        pytest.param(
            [_SEMGREP_OK],
            _STATIC,
            "error",
            "BLOCK",
            "not_finished",
            id="young_running",
        ),
        pytest.param(
            [_SEMGREP_OK],
            _STATIC,
            "error",
            "BLOCK",
            "not_finished",
            id="finished_at_null",
        ),
        pytest.param(
            [_SEMGREP_OK],
            _STATIC,
            "timeout",
            "BLOCK",
            "timeout",
            id="duplicate_run",
        ),
        pytest.param([], _STATIC, "timeout", "BLOCK", "timeout", id="timeout"),
        pytest.param([], _STATIC, "timeout", "BLOCK", "timeout", id="stalled_running"),
        pytest.param([], _STATIC, "completed", "BLOCK", "no_findings", id="no_findings"),
        pytest.param(
            [_finding("canary", "canary.tripped", "critical")],
            _STATIC,
            "completed",
            "BLOCK",
            "canary",
            id="canary",
        ),
        pytest.param(
            [_finding("reader", "reader_invalid", "error"), _SEMGREP_OK],
            _STATIC,
            "completed",
            "BLOCK",
            "reader_error",
            id="reader_error",
        ),
        pytest.param(
            [_finding("policy", "ruleset_empty", "error")],
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            id="policy_error",
        ),
        pytest.param(
            [_finding("semgrep", "semgrep.error", "error")],
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            id="semgrep_error",
        ),
        pytest.param(
            [_SEMGREP_OK, _finding("jail", "egress", "high")],
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            id="jail_high",
        ),
        pytest.param(
            [_finding("semgrep", "rule.high", "high")],
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            id="high",
        ),
        pytest.param(
            [_finding("semgrep", "rule.critical", "critical")],
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            id="critical",
        ),
        pytest.param(
            [
                _finding("semgrep", "rule.high", "high"),
                _finding("semgrep", "rule.medium", "medium"),
            ],
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            id="high_plus_medium",
        ),
        pytest.param(
            [_finding("reader", "false_safety_claim", "medium")],
            _STATIC,
            "completed",
            "BLOCK",
            "semgrep_missing",
            id="reader_medium",
        ),
        pytest.param(
            [_finding("semgrep", "rule.medium", "medium")],
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            id="semgrep_medium",
        ),
        pytest.param(
            [_SEMGREP_OK],
            _STATIC,
            "completed",
            "ALLOW",
            "clean",
            id="clean_info",
        ),
        pytest.param(
            [_finding("semgrep", "rule.low", "low")],
            _STATIC,
            "completed",
            "ALLOW",
            "clean",
            id="low_only",
        ),
        pytest.param(
            [_SEMGREP_OK],
            frozenset({"static", "reader"}),
            "completed",
            "BLOCK",
            "reader_missing",
            id="reader_missing",
        ),
        pytest.param(
            [_SEMGREP_OK],
            frozenset({"static", "detonation"}),
            "completed",
            "BLOCK",
            "detonation_missing",
            id="detonation_missing",
        ),
    ],
)
def test_decide(findings, stages, status, decision, reason):
    verdict = decide(findings, stages, status)
    assert verdict.decision == decision
    assert verdict.reason == reason
