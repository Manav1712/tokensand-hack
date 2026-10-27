import json
from pathlib import Path

import pytest

from skill_warden.models import Finding, Report, Severity, Source, Verdict
from skill_warden.reader import ReaderResult

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison"
PROSE = ROOT / "fixtures" / "skills" / "prose-exfil"
_SECRET = "sk-warden-fake-key-7c2e9a4b"


def _skill(tmp_path: Path) -> Path:
    path = tmp_path / "skill"
    path.mkdir()
    (path / "SKILL.md").write_text("hello\n", encoding="utf-8")
    return path


def _report(decision: str, reason: str, detail: str = "") -> Report:
    return Report((), Verdict(decision, reason, detail))


def test_clean_date_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    from skill_warden.cli import main

    code = main(["scan", str(CLEAN), "--no-history"])

    captured = capsys.readouterr().out
    assert code == 0
    assert "ALLOW" in captured
    assert "clean" in captured


def test_memory_poison_exits_20(capsys: pytest.CaptureFixture[str]) -> None:
    from skill_warden.cli import main

    code = main(["scan", str(MEMORY), "--no-history"])

    captured = capsys.readouterr()
    assert code == 20
    assert "BLOCK" in captured.out
    assert "high_finding" in captured.out
    assert "Traceback" not in captured.err


def test_several_paths_exit_with_the_worst(capsys: pytest.CaptureFixture[str]) -> None:
    from skill_warden.cli import main

    code = main(["scan", str(CLEAN), str(MEMORY), "--format", "json", "--no-history"])

    body = json.loads(capsys.readouterr().out)
    assert code == 20
    assert body["schema"] == "skill-warden/scan@1"
    assert set(body) == {"schema", "summary", "reports"}
    assert body["summary"]["skills"] == 2
    assert body["summary"]["worst"] == "BLOCK"
    assert body["summary"]["counts"] == {"BLOCK": 1, "ASK": 0, "ALLOW": 1}
    assert [item["verdict"]["decision"] for item in body["reports"]] == ["ALLOW", "BLOCK"]
    assert body["reports"][1]["verdict"]["reason"] == "high_finding"
    assert body["reports"][0]["skill"]["path"] == str(CLEAN)


@pytest.mark.parametrize(
    ("decisions", "code"),
    [
        (("ALLOW",), 0),
        (("ASK",), 10),
        (("BLOCK",), 20),
        (("ALLOW", "ASK"), 10),
        (("ASK", "BLOCK"), 20),
        (("ALLOW", "BLOCK"), 20),
    ],
)
def test_exit_code_is_the_worst_verdict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    decisions: tuple[str, ...],
    code: int,
) -> None:
    from skill_warden.cli import main

    paths = []
    reports = []
    for index, decision in enumerate(decisions):
        path = tmp_path / f"skill-{index}"
        path.mkdir()
        (path / "SKILL.md").write_text("hello\n", encoding="utf-8")
        paths.append(path)
        reason = {"ALLOW": "clean", "ASK": "medium_only", "BLOCK": "high_finding"}[decision]
        reports.append(_report(decision, reason))

    def fake_scan(got, *, llm, detonate, history):
        assert list(got) == paths
        assert llm is None
        assert detonate is False
        assert history is False
        return tuple(reports)

    monkeypatch.setattr("skill_warden.cli.scan", fake_scan)

    assert main(["scan", *[str(path) for path in paths], "--no-history"]) == code


def test_detonate_and_model_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from skill_warden.cli import main

    skill = _skill(tmp_path)
    seen: dict[str, object] = {}

    class FakeReader:
        def __init__(self, api_key: str, base_url: str, model: str) -> None:
            seen["api_key"] = api_key
            seen["base_url"] = base_url
            seen["model"] = model

        def call(self, text: str) -> dict[str, list[str]]:
            seen["called"] = text
            return {"flags": [], "evidence": []}

    def fake_scan(paths, *, llm, detonate, history):
        seen["paths"] = list(paths)
        seen["llm"] = llm
        seen["detonate"] = detonate
        seen["history"] = history
        llm.call("ignored")
        return (_report("ALLOW", "clean"),)

    monkeypatch.setattr("skill_warden.cli.Reader", FakeReader)
    monkeypatch.setattr("skill_warden.cli.scan", fake_scan)
    monkeypatch.setenv("SKILL_WARDEN_LLM_KEY", _SECRET)

    code = main(
        [
            "scan",
            str(skill),
            "--llm",
            "openai-compatible:dummy-model",
            "--llm-base-url",
            "http://127.0.0.1:9/v1",
            "--llm-key-env",
            "SKILL_WARDEN_LLM_KEY",
            "--detonate",
            "--no-history",
        ]
    )

    assert code == 0
    assert seen["paths"] == [skill]
    assert seen["detonate"] is True
    assert seen["history"] is False
    assert seen["model"] == "dummy-model"
    assert seen["base_url"] == "http://127.0.0.1:9/v1"
    assert seen["api_key"] == _SECRET
    assert seen["llm"] is not None
    assert seen["called"] == "ignored"


def test_scripted_reader_blocks_prose_exfil(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from skill_warden.cli import main

    secret = "sk-warden-scripted-key-11aa"

    class Scripted:
        def __init__(self, api_key: str, base_url: str, model: str) -> None:
            assert api_key == secret
            assert base_url == "http://127.0.0.1:9/v1"
            assert model == "scripted"

        def call(self, text: str) -> ReaderResult:
            assert "example.invalid" in text
            return ReaderResult(["credential_exfil"], ["sent the note"])

    monkeypatch.setattr("skill_warden.cli.Reader", Scripted)
    monkeypatch.setenv("SKILL_WARDEN_LLM_KEY", secret)

    code = main(
        [
            "scan",
            str(PROSE),
            "--llm",
            "openai-compatible:scripted",
            "--llm-base-url",
            "http://127.0.0.1:9/v1",
            "--llm-key-env",
            "SKILL_WARDEN_LLM_KEY",
            "--no-history",
        ]
    )

    captured = capsys.readouterr()
    assert code == 20
    assert "BLOCK" in captured.out
    assert "high_finding" in captured.out
    assert "credential_exfil" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err


def test_env_key_never_appears_in_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from skill_warden.cli import main

    skill = _skill(tmp_path)
    finding = Finding(
        source=Source.SEMGREP,
        rule_id="demo.rule",
        severity=Severity.HIGH,
        excerpt=f"send {_SECRET} now",
    )
    report = Report((finding,), Verdict("BLOCK", "high_finding", "demo.rule"))

    def fake_scan(paths, *, llm, detonate, history):
        assert llm is None
        assert detonate is False
        assert history is True
        return (report,)

    monkeypatch.setattr("skill_warden.cli.scan", fake_scan)
    monkeypatch.setenv("OPENAI_API_KEY", _SECRET)

    code = main(["scan", str(skill), "--format", "json"])

    captured = capsys.readouterr()
    assert code == 20
    assert _SECRET not in captured.out
    assert _SECRET not in captured.err
    assert "[redacted]" in captured.out
    body = json.loads(captured.out)
    assert body["schema"] == "skill-warden/scan@1"


def test_failed_reader_does_not_print_the_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from skill_warden.cli import main

    secret = "sk-warden-fake-key-llm-bb19"
    monkeypatch.setenv("SKILL_WARDEN_LLM_KEY", secret)

    code = main(
        [
            "scan",
            str(CLEAN),
            "--llm",
            "openai-compatible:dummy",
            "--llm-base-url",
            "http://127.0.0.1:9",
            "--llm-key-env",
            "SKILL_WARDEN_LLM_KEY",
            "--no-history",
        ]
    )

    captured = capsys.readouterr()
    assert code == 20
    assert "BLOCK" in captured.out
    assert "not_finished" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_no_history_writes_nothing(history_home: Path) -> None:
    from skill_warden.cli import main

    assert main(["scan", str(CLEAN), "--no-history"]) == 0
    assert not (history_home / "history.sqlite3").exists()


def test_scan_appends_history(history_home: Path) -> None:
    from skill_warden.cli import main

    assert main(["scan", str(MEMORY), "--format", "text"]) == 20
    assert (history_home / "history.sqlite3").is_file()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["scan"],
        ["dance"],
        ["scan", "--format", "xml", "PLACE"],
        ["scan", "PLACE", "--llm", "no-colon"],
        ["scan", "PLACE", "--llm", ":model"],
        ["scan", "PLACE", "--llm", "openai-compatible:"],
        ["scan", "PLACE", "--llm", "openai-compatible:demo"],
        [
            "scan",
            "PLACE",
            "--llm",
            "openai-compatible:demo",
            "--llm-base-url",
            "http://127.0.0.1:9",
        ],
        [
            "scan",
            "PLACE",
            "--llm",
            "openai-compatible:demo",
            "--llm-key-env",
            "SKILL_WARDEN_LLM_KEY",
        ],
        [
            "scan",
            "PLACE",
            "--llm",
            "openai-compatible:demo",
            "--llm-base-url",
            "http://127.0.0.1:9",
            "--llm-key-env",
            "SKILL_WARDEN_LLM_KEY",
        ],
    ],
)
def test_bad_input_exits_2(
    argv: list[str],
    history_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skill_warden.cli import main

    skill = _skill(tmp_path)
    monkeypatch.delenv("SKILL_WARDEN_LLM_KEY", raising=False)
    command = [str(skill) if item == "PLACE" else item for item in argv]
    assert main(command) == 2
    assert not (history_home / "history.sqlite3").exists()


def test_missing_directory_exits_2(tmp_path: Path, history_home: Path) -> None:
    from skill_warden.cli import main

    missing = tmp_path / "missing"
    assert main(["scan", str(missing), "--format", "json"]) == 2
    assert not (history_home / "history.sqlite3").exists()


def test_file_path_exits_2(tmp_path: Path, history_home: Path) -> None:
    from skill_warden.cli import main

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("hello\n", encoding="utf-8")
    assert main(["scan", str(skill_file)]) == 2
    assert not (history_home / "history.sqlite3").exists()
