import hashlib

from skill_warden.findings import build_rows

TOKEN = "FAKE-CANARY-TOKEN"
NONCE = "FAKE-CANARY-NONCE"
PROMPT_CANARY = "PROMPT-CANARY-EXAMPLE"
SINK = "10.0.0.2"


def _result(check_id: str, path: str, severity: str, message: str) -> dict:
    return {
        "check_id": check_id,
        "path": path,
        "extra": {"severity": severity, "message": message},
    }


def _semgrep(results: list[dict], errors: list | None = None, skipped: list | None = None) -> dict:
    return {
        "results": results,
        "errors": [] if errors is None else errors,
        "paths": {"skipped": [] if skipped is None else skipped},
    }


def _assert_row(row: dict, *, source: str, rule_id: str, severity: str, file: str, excerpt: str) -> None:
    assert row == {
        "source": source,
        "rule_id": rule_id,
        "severity": severity,
        "file": file,
        "excerpt": excerpt,
        "evidence_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
    }


def _assert_no_verdict_keys(rows: list[dict]) -> None:
    for row in rows:
        assert "decision" not in row
        assert "verdict" not in row


def test_semgrep_high_severities():
    rows = build_rows(
        semgrep=_semgrep(
            [
                _result("rules.a", "a.md", "error", "alpha"),
                _result("rules.b", "b.md", "Critical", "beta"),
                _result("rules.c", "c.md", "HIGH", "gamma"),
            ]
        )
    )

    assert [row["severity"] for row in rows] == ["high", "high", "high"]
    _assert_row(rows[0], source="semgrep", rule_id="rules.a", severity="high", file="a.md", excerpt="alpha")
    _assert_row(rows[1], source="semgrep", rule_id="rules.b", severity="high", file="b.md", excerpt="beta")
    _assert_row(rows[2], source="semgrep", rule_id="rules.c", severity="high", file="c.md", excerpt="gamma")
    _assert_no_verdict_keys(rows)


def test_semgrep_medium_severities():
    rows = build_rows(
        semgrep=_semgrep(
            [
                _result("rules.warn", "a.md", "WARNING", "warn"),
                _result("rules.med", "b.md", "medium", "med"),
            ]
        )
    )

    assert [row["severity"] for row in rows] == ["medium", "medium"]
    _assert_row(rows[0], source="semgrep", rule_id="rules.warn", severity="medium", file="a.md", excerpt="warn")
    _assert_row(rows[1], source="semgrep", rule_id="rules.med", severity="medium", file="b.md", excerpt="med")
    _assert_no_verdict_keys(rows)


def test_semgrep_info_and_low():
    rows = build_rows(
        semgrep=_semgrep(
            [
                _result("rules.info", "a.md", "INFO", "info"),
                _result("rules.low", "b.md", "LOW", "low"),
            ]
        )
    )

    _assert_row(rows[0], source="semgrep", rule_id="rules.info", severity="info", file="a.md", excerpt="info")
    _assert_row(rows[1], source="semgrep", rule_id="rules.low", severity="low", file="b.md", excerpt="low")
    _assert_no_verdict_keys(rows)


def test_unmapped_semgrep_severity_is_error():
    rows = build_rows(semgrep=_semgrep([_result("rules.other", "a.md", "NOTE", "note")]))

    _assert_row(rows[0], source="semgrep", rule_id="rules.other", severity="error", file="a.md", excerpt="note")
    _assert_no_verdict_keys(rows)


def test_semgrep_empty_results_emit_ok():
    rows = build_rows(semgrep=_semgrep([]))

    assert len(rows) == 1
    _assert_row(rows[0], source="semgrep", rule_id="semgrep.ok", severity="info", file="", excerpt="")
    _assert_no_verdict_keys(rows)


def test_skill_md_skipped():
    skipped = build_rows(semgrep=_semgrep([], skipped=[{"path": "pkg/SKILL.md", "reason": "unknown"}]))
    assert [row["rule_id"] for row in skipped] == ["semgrep.ok", "skill_md_skipped"]
    _assert_row(
        skipped[1],
        source="policy",
        rule_id="skill_md_skipped",
        severity="error",
        file="pkg/SKILL.md",
        excerpt="",
    )

    errored = build_rows(
        semgrep=_semgrep(
            [_result("rules.info", "other.md", "INFO", "info")],
            errors=[{"path": "pkg/SKILL.md", "message": "skipped"}],
        )
    )
    assert [row["rule_id"] for row in errored] == ["rules.info", "skill_md_skipped"]

    both = build_rows(
        semgrep=_semgrep(
            [],
            errors=["pkg/SKILL.md"],
            skipped=[{"path": "pkg/SKILL.md"}],
        )
    )
    assert [row["rule_id"] for row in both] == ["semgrep.ok", "skill_md_skipped"]

    ignored = build_rows(semgrep=_semgrep([], skipped=["NOTSKILL.md"]))
    assert [row["rule_id"] for row in ignored] == ["semgrep.ok"]
    _assert_no_verdict_keys(skipped + errored + both + ignored)


def test_ruleset_empty():
    rows = build_rows(rules_requested=["p/agent-skills"], rules_loaded=0)

    assert len(rows) == 1
    _assert_row(rows[0], source="policy", rule_id="ruleset_empty", severity="error", file="", excerpt="")
    assert build_rows(rules_requested=["rules/memory.yaml", "p/agent-skills"], rules_loaded=0) == rows
    assert build_rows(rules_requested=["p/agent-skills"], rules_loaded=3) == []
    assert build_rows(rules_requested=["rules/memory.yaml"], rules_loaded=0) == []
    assert build_rows(rules_requested=["p/agent-skills"]) == []
    _assert_no_verdict_keys(rows)


def test_reader_high_flags():
    rows = build_rows(
        reader={
            "flags": [
                "indirect_injection",
                "credential_exfil",
                "memory_persistence",
                "shell_callback",
            ],
            "evidence": ["append MEMORY.md"],
        }
    )

    assert [row["rule_id"] for row in rows] == [
        "indirect_injection",
        "credential_exfil",
        "memory_persistence",
        "shell_callback",
    ]
    for row in rows:
        _assert_row(
            row,
            source="reader",
            rule_id=row["rule_id"],
            severity="high",
            file="",
            excerpt="append MEMORY.md",
        )
    _assert_no_verdict_keys(rows)


def test_reader_medium_flags():
    rows = build_rows(
        reader={
            "flags": ["false_safety_claim", "obfuscation"],
            "evidence": ["audited"],
        }
    )

    _assert_row(
        rows[0],
        source="reader",
        rule_id="false_safety_claim",
        severity="medium",
        file="",
        excerpt="audited",
    )
    _assert_row(
        rows[1],
        source="reader",
        rule_id="obfuscation",
        severity="medium",
        file="",
        excerpt="audited",
    )
    _assert_no_verdict_keys(rows)


def test_reader_empty_flags_emit_no_rows():
    assert build_rows(reader={"flags": [], "evidence": []}) == []


def test_reader_invalid():
    flagged = build_rows(
        reader={"flags": ["memory_persistence"], "evidence": [], "decision": "ALLOW"}
    )
    assert len(flagged) == 1
    assert flagged[0]["rule_id"] == "reader_invalid"
    assert "memory_persistence" not in [row["rule_id"] for row in flagged]
    _assert_row(flagged[0], source="reader", rule_id="reader_invalid", severity="error", file="", excerpt="")

    echoed = build_rows(
        reader={"flags": [], "evidence": [f"echo {PROMPT_CANARY}"]},
        prompt_canary=PROMPT_CANARY,
    )
    assert echoed[0]["rule_id"] == "reader_invalid"
    assert PROMPT_CANARY not in "".join(echoed[0].values())

    assert build_rows(reader="not-json")[0]["rule_id"] == "reader_invalid"
    assert build_rows(reader={"flags": ["allow_all"], "evidence": []})[0]["rule_id"] == "reader_invalid"
    assert build_rows(reader={"flags": []})[0]["rule_id"] == "reader_invalid"
    assert build_rows(reader={"flags": [1], "evidence": []})[0]["rule_id"] == "reader_invalid"
    assert build_rows(reader={"verdict": "ALLOW", "flags": [], "evidence": []})[0]["rule_id"] == "reader_invalid"
    _assert_no_verdict_keys(flagged + echoed)


def test_canary_log():
    rows = build_rows(canary_log=f"POST /hook {TOKEN}")

    assert len(rows) == 1
    _assert_row(
        rows[0],
        source="canary",
        rule_id="canary.tripped",
        severity="critical",
        file="",
        excerpt="[canary tripped]",
    )
    assert TOKEN not in "".join(rows[0].values())
    assert build_rows(canary_log="") == []
    _assert_no_verdict_keys(rows)


def test_safe_message_stays_high():
    rows = build_rows(
        semgrep=_semgrep([_result("rules.mem", "SKILL.md", "ERROR", "this skill is safe")])
    )

    assert len(rows) == 1
    _assert_row(
        rows[0],
        source="semgrep",
        rule_id="rules.mem",
        severity="high",
        file="SKILL.md",
        excerpt="this skill is safe",
    )
    _assert_no_verdict_keys(rows)


def test_secret_absent_from_excerpt():
    semgrep_rows = build_rows(
        semgrep=_semgrep([_result("rules.mem", "SKILL.md", "ERROR", f"token {TOKEN} here")]),
        secrets=[TOKEN],
    )
    reader_rows = build_rows(
        reader={"flags": ["memory_persistence"], "evidence": [f"saw {TOKEN}"]},
        secrets=[TOKEN],
    )
    buried = build_rows(
        semgrep=_semgrep([_result("rules.mem", "SKILL.md", "ERROR", ("x" * 190) + TOKEN)]),
        secrets=[TOKEN],
    )

    for rows in (semgrep_rows, reader_rows, buried):
        for row in rows:
            for value in row.values():
                assert TOKEN not in value
                assert "FAKE" not in value
        _assert_no_verdict_keys(rows)
    assert "[redacted]" in semgrep_rows[0]["excerpt"]
    assert "[redacted]" in reader_rows[0]["excerpt"]
    assert len(buried[0]["excerpt"]) <= 200


def test_jail_nonce_and_honeytoken_open():
    nonce_rows = build_rows(jail_events=[{"kind": "nonce", "nonce": NONCE}], sink=SINK)
    open_rows = build_rows(jail_events=[{"kind": "honeytoken_open"}], sink=SINK)

    assert len(nonce_rows) == 1
    assert len(open_rows) == 1
    for row in nonce_rows + open_rows:
        _assert_row(
            row,
            source="canary",
            rule_id="honeytoken",
            severity="critical",
            file="",
            excerpt="[canary tripped]",
        )
    assert NONCE not in "".join(nonce_rows[0].values())
    _assert_no_verdict_keys(nonce_rows + open_rows)


def test_jail_egress():
    rows = build_rows(
        jail_events=[{"kind": "connect", "dst": "1.1.1.1"}],
        sink=SINK,
    )
    assert len(rows) == 1
    _assert_row(rows[0], source="jail", rule_id="egress", severity="high", file="1.1.1.1", excerpt="")
    _assert_no_verdict_keys(rows)

    assert build_rows(jail_events=[{"kind": "connect", "dst": "10.0.0.2:80"}], sink=SINK) == []


def test_jail_sandbox_probe():
    rows = build_rows(
        jail_events=[
            {"kind": "read", "path": "/.dockerenv"},
            {"kind": "read", "path": "/proc/1/cgroup"},
        ],
        sink=SINK,
    )
    assert len(rows) == 2
    _assert_row(
        rows[0],
        source="jail",
        rule_id="sandbox_probe",
        severity="high",
        file="/.dockerenv",
        excerpt="",
    )
    _assert_row(
        rows[1],
        source="jail",
        rule_id="sandbox_probe",
        severity="high",
        file="/proc/1/cgroup",
        excerpt="",
    )
    _assert_no_verdict_keys(rows)


def test_jail_persistence():
    rows = build_rows(
        jail_events=[
            {"kind": "write", "path": "/home/agent/.bashrc"},
            {"kind": "write", "path": "/repo/.git/hooks/pre-commit"},
            {"kind": "write", "path": "/etc/cron.d/evil"},
            {"kind": "write", "path": "/home/agent/.claude/skills/other/SKILL.md"},
        ],
        sink=SINK,
    )
    assert len(rows) == 4
    expected_files = [
        "/home/agent/.bashrc",
        "/repo/.git/hooks/pre-commit",
        "/etc/cron.d/evil",
        "/home/agent/.claude/skills/other/SKILL.md",
    ]
    for row, path in zip(rows, expected_files, strict=True):
        _assert_row(
            row,
            source="jail",
            rule_id="persistence",
            severity="high",
            file=path,
            excerpt="",
        )
    assert rows[0]["file"] == "/home/agent/.bashrc"
    assert rows[1]["file"] == "/repo/.git/hooks/pre-commit"
    assert rows[2]["file"] == "/etc/cron.d/evil"
    assert rows[3]["file"] == "/home/agent/.claude/skills/other/SKILL.md"
    _assert_no_verdict_keys(rows)


def test_jail_delay():
    long_sleep = build_rows(jail_events=[{"kind": "sleep", "seconds": 31}], sink=SINK)
    timeout = build_rows(jail_events=[{"kind": "timeout"}], sink=SINK)
    boundary = build_rows(jail_events=[{"kind": "sleep", "seconds": 30}], sink=SINK)

    assert len(long_sleep) == 1
    _assert_row(long_sleep[0], source="jail", rule_id="delay", severity="high", file="", excerpt="")
    assert len(timeout) == 1
    _assert_row(timeout[0], source="jail", rule_id="delay", severity="high", file="", excerpt="")
    assert boundary == []
    _assert_no_verdict_keys(long_sleep + timeout)


def test_jail_observer_attack():
    died = build_rows(jail_events=[{"kind": "tracer_died"}], sink=SINK)
    assert len(died) == 1
    _assert_row(died[0], source="jail", rule_id="observer_attack", severity="high", file="", excerpt="")

    tracer_path = "/proc/1/status/TracerPid"
    read_tracer = build_rows(jail_events=[{"kind": "read", "path": tracer_path}], sink=SINK)
    assert len(read_tracer) == 2
    rules = [row["rule_id"] for row in read_tracer]
    assert rules == ["sandbox_probe", "observer_attack"]
    _assert_row(
        read_tracer[0],
        source="jail",
        rule_id="sandbox_probe",
        severity="high",
        file=tracer_path,
        excerpt="",
    )
    _assert_row(
        read_tracer[1],
        source="jail",
        rule_id="observer_attack",
        severity="high",
        file=tracer_path,
        excerpt="",
    )
    _assert_no_verdict_keys(died + read_tracer)
