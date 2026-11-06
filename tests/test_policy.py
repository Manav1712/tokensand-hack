from collections.abc import Collection, Sequence
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skill_warden.models import Approval, Finding, RunOutcome, Severity, Source, Verdict
from skill_warden.policy import block_not_finished, decide

_STATIC = frozenset({"static"})
_OK = ("semgrep", "semgrep.ok", "info")
_SOURCES = ("intake", "semgrep", "reader", "jail", "canary", "policy")
_SEVERITIES = ("info", "low", "medium", "high", "critical", "error")
_STAGES = ("static", "reader", "detonation")
_RULES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8)


def _finding(source: str, rule_id: str, severity: str) -> Finding:
    return Finding(Source(source), rule_id, Severity(severity))


def _outcome(
    findings: Sequence[tuple[str, str, str]],
    stages: Collection[str],
    status: str,
) -> RunOutcome:
    return RunOutcome(
        uuid4(),
        status,  # type: ignore[arg-type]
        frozenset(stages),  # type: ignore[arg-type]
        tuple(_finding(*item) for item in findings),
        "abc",
        1,
    )


@pytest.mark.parametrize(
    ("findings", "stages", "status", "decision", "reason", "detail"),
    [
        pytest.param((), _STATIC, "error", "BLOCK", "not_finished", "", id="missing_run"),
        pytest.param((_OK,), _STATIC, "error", "BLOCK", "not_finished", "", id="young_running"),
        pytest.param(
            (_OK,),
            _STATIC,
            "error",
            "BLOCK",
            "not_finished",
            "",
            id="finished_at_null",
        ),
        pytest.param((_OK,), _STATIC, "timeout", "BLOCK", "timeout", "", id="duplicate_run"),
        pytest.param((), _STATIC, "timeout", "BLOCK", "timeout", "", id="timeout"),
        pytest.param((), _STATIC, "timeout", "BLOCK", "timeout", "", id="stalled_running"),
        pytest.param(
            (("canary", "canary.tripped", "critical"),),
            _STATIC,
            "timeout",
            "BLOCK",
            "timeout",
            "",
            id="timeout_with_canary",
        ),
        pytest.param((), _STATIC, "completed", "BLOCK", "no_findings", "", id="no_findings"),
        pytest.param(
            (("canary", "canary.tripped", "critical"),),
            _STATIC,
            "completed",
            "BLOCK",
            "canary",
            "canary.tripped",
            id="canary",
        ),
        pytest.param(
            (
                ("semgrep", "rule.high", "high"),
                ("canary", "canary_egress", "critical"),
            ),
            _STATIC,
            "completed",
            "BLOCK",
            "canary",
            "canary_egress",
            id="canary_after_high",
        ),
        pytest.param(
            (
                ("jail", "sandbox_probe", "medium"),
                ("canary", "canary_egress", "critical"),
            ),
            _STATIC,
            "completed",
            "BLOCK",
            "canary",
            "canary_egress",
            id="sandbox_probe_plus_canary",
        ),
        pytest.param(
            (
                ("semgrep", "semgrep.error", "error"),
                ("reader", "reader_invalid", "error"),
            ),
            _STATIC,
            "completed",
            "BLOCK",
            "reader_error",
            "reader_invalid",
            id="reader_error",
        ),
        pytest.param(
            (_OK, ("reader", "reader_refused", "error")),
            _STATIC,
            "completed",
            "BLOCK",
            "reader_error",
            "reader_refused",
            id="reader_refused",
        ),
        pytest.param(
            (_OK, ("policy", "ruleset_empty", "error")),
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            "ruleset_empty",
            id="policy_error",
        ),
        pytest.param(
            (("semgrep", "semgrep.error", "error"),),
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            "semgrep.error",
            id="semgrep_error",
        ),
        pytest.param(
            (_OK, ("intake", "symlink", "error")),
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            "symlink",
            id="symlink",
        ),
        pytest.param(
            (
                _OK,
                ("jail", "egress", "high"),
                ("jail", "coverage_incomplete", "error"),
            ),
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            "coverage_incomplete",
            id="coverage_incomplete",
        ),
        pytest.param(
            (_OK, ("jail", "isolation_failed", "error")),
            _STATIC,
            "completed",
            "BLOCK",
            "tool_error",
            "isolation_failed",
            id="isolation_failed",
        ),
        pytest.param(
            (_OK, ("jail", "egress", "high")),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "egress",
            id="jail_high",
        ),
        pytest.param(
            (("semgrep", "rule.high", "high"),),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "rule.high",
            id="high",
        ),
        pytest.param(
            (("semgrep", "rule.critical", "critical"),),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "rule.critical",
            id="critical",
        ),
        pytest.param(
            (
                ("semgrep", "rule.high", "high"),
                ("semgrep", "rule.medium", "medium"),
            ),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "rule.high",
            id="high_plus_medium",
        ),
        pytest.param(
            (_OK, ("jail", "delay", "high")),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "delay",
            id="delay",
        ),
        pytest.param(
            (_OK, ("intake", "case_collision", "high")),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "case_collision",
            id="case_collision",
        ),
        pytest.param(
            (_OK, ("intake", "frontmatter_mismatch_install", "high")),
            _STATIC,
            "completed",
            "BLOCK",
            "high_finding",
            "frontmatter_mismatch_install",
            id="frontmatter_mismatch_install",
        ),
        pytest.param(
            (("reader", "false_safety_claim", "medium"),),
            _STATIC,
            "completed",
            "BLOCK",
            "semgrep_missing",
            "",
            id="reader_medium",
        ),
        pytest.param(
            (_OK,),
            frozenset({"static", "reader"}),
            "completed",
            "BLOCK",
            "reader_missing",
            "",
            id="reader_missing",
        ),
        pytest.param(
            (_OK,),
            frozenset({"static", "detonation"}),
            "completed",
            "BLOCK",
            "detonation_missing",
            "",
            id="detonation_missing",
        ),
        pytest.param(
            (
                ("semgrep", "rule.low", "low"),
                ("semgrep", "rule.medium", "medium"),
            ),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "rule.medium",
            id="semgrep_medium",
        ),
        pytest.param(
            (_OK, ("reader", "reader_primary_refused", "medium")),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "reader_primary_refused",
            id="reader_primary_refused",
        ),
        pytest.param(
            (_OK, ("intake", "obfuscation.unicode", "medium")),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "obfuscation.unicode",
            id="obfuscation_unicode",
        ),
        pytest.param(
            (_OK, ("jail", "sandbox_probe", "medium")),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "sandbox_probe",
            id="sandbox_probe",
        ),
        pytest.param(
            (_OK, ("jail", "command_timeout", "medium")),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "command_timeout",
            id="command_timeout",
        ),
        pytest.param(
            (_OK, ("intake", "frontmatter_complex", "medium")),
            _STATIC,
            "completed",
            "ASK",
            "medium_only",
            "frontmatter_complex",
            id="frontmatter_complex",
        ),
        pytest.param((_OK,), _STATIC, "completed", "ALLOW", "clean", "", id="clean_info"),
        pytest.param(
            (("semgrep", "rule.low", "low"),),
            _STATIC,
            "completed",
            "ALLOW",
            "clean",
            "",
            id="low_only",
        ),
        pytest.param(
            (_OK, ("jail", "env_probe", "low")),
            _STATIC,
            "completed",
            "ALLOW",
            "clean",
            "",
            id="env_probe",
        ),
        pytest.param(
            (_OK, ("reader", "reader.ok", "info")),
            frozenset({"static", "reader"}),
            "completed",
            "ALLOW",
            "clean",
            "",
            id="reader_ok",
        ),
        pytest.param(
            (_OK, ("jail", "jail.ok", "info")),
            frozenset({"static", "detonation"}),
            "completed",
            "ALLOW",
            "clean",
            "",
            id="jail_ok",
        ),
        pytest.param(
            (("reader", "reader.ok", "info"),),
            frozenset({"reader"}),
            "completed",
            "ALLOW",
            "clean",
            "",
            id="reader_only",
        ),
        pytest.param(
            (("jail", "jail.ok", "info"),),
            frozenset({"detonation"}),
            "completed",
            "ALLOW",
            "clean",
            "",
            id="detonation_only",
        ),
    ],
)
def test_decide(findings, stages, status, decision, reason, detail):
    verdict = decide(_outcome(findings, stages, status))

    assert verdict.decision == decision
    assert verdict.reason == reason
    assert verdict.detail == detail
    assert verdict.approval is None


def test_block_not_finished():
    assert block_not_finished() == Verdict("BLOCK", "not_finished")


def test_approval_is_ignored_until_covered_findings():
    outcome = RunOutcome(
        uuid4(),
        "completed",
        _STATIC,
        (_finding("semgrep", "rule.high", "high"),),
        "abc",
        2,
    )
    approval = Approval(
        "ap-1",
        "abc",
        2,
        frozenset({"rule.high"}),
        "its job",
        "2026-11-05",
        uuid4(),
    )

    verdict = decide(outcome, approval)

    assert verdict == decide(outcome)
    assert verdict.decision == "BLOCK"
    assert verdict.reason == "high_finding"
    assert verdict.detail == "rule.high"
    assert verdict.approval is None


_finding_rows = st.lists(
    st.tuples(st.sampled_from(_SOURCES), _RULES, st.sampled_from(_SEVERITIES)),
    max_size=4,
)
_stages = st.lists(st.sampled_from(_STAGES), max_size=3, unique=True)
_blocking = st.one_of(
    st.tuples(st.just("canary"), _RULES, st.sampled_from(_SEVERITIES)),
    st.tuples(st.sampled_from(_SOURCES), _RULES, st.just("error")),
    st.tuples(st.sampled_from(_SOURCES), _RULES, st.sampled_from(("high", "critical"))),
)


@given(_finding_rows, _stages, st.sampled_from(("completed", "timeout", "error")))
def test_decide_is_deterministic(findings, stages, status):
    outcome = _outcome(findings, stages, status)

    assert decide(outcome) == decide(outcome)


@given(_finding_rows, _blocking, _finding_rows, _finding_rows, _stages)
def test_adding_findings_keeps_a_block(prefix, blocking, suffix, extra, stages):
    base = _outcome((*prefix, blocking, *suffix), stages, "completed")
    added = _outcome((*extra, *prefix, blocking, *suffix, *extra), stages, "completed")

    assert decide(base).decision == "BLOCK"
    assert decide(added).decision == decide(base).decision
