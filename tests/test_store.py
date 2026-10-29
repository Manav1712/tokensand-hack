import uuid

import pytest

from skill_warden.errors import RedactionError
from skill_warden.store import Store

pytestmark = pytest.mark.docker


def _finding(rule_id: str, severity: str, excerpt: str = "") -> dict[str, str]:
    return {
        "source": "semgrep",
        "rule_id": rule_id,
        "severity": severity,
        "file": "",
        "evidence_hash": rule_id,
        "excerpt": excerpt,
    }


def test_completed_semgrep_ok_is_allow(scanner):
    store = Store(scanner)
    run_id = uuid.uuid4()
    store.insert_run(run_id, "hash")
    store.insert_findings(run_id, [_finding("semgrep.ok", "info")])
    store.finish_run(run_id, "completed")

    assert store.verdict(run_id) == ("ALLOW", "clean")


def test_high_finding_is_block(scanner):
    store = Store(scanner)
    run_id = uuid.uuid4()
    store.insert_run(run_id, "hash")
    store.insert_findings(run_id, [_finding("rule.high", "high")])
    store.finish_run(run_id, "completed")

    assert store.verdict(run_id) == ("BLOCK", "high_finding")


def test_unredacted_excerpt_is_refused(scanner):
    store = Store(scanner, secrets=["FAKE-CANARY-TOKEN"])
    run_id = uuid.uuid4()
    row = _finding("rule.high", "high", "token FAKE-CANARY-TOKEN here")

    with pytest.raises(RedactionError):
        store.insert_findings(run_id, [row])

    result = scanner.query(
        "SELECT count() FROM skill_warden.findings WHERE run_id = {run_id:UUID}",
        parameters={"run_id": str(run_id)},
    )
    assert result.result_rows[0][0] == 0
