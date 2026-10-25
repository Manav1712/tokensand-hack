import json
import sqlite3
from pathlib import Path

import pytest

from skill_warden.cli import main
from skill_warden.models import Report, Verdict
from skill_warden.reader import ReaderResult

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "fixtures" / "skills" / "clean-date"
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison"
_KEY = "sk-test-warden-FAKE-KEY-0123456789abcdef"
_UNUSED = "sk-test-warden-UNUSED-SENTINEL-fedcba9876543210"
_EXIT = {"ALLOW": 0, "ASK": 10, "BLOCK": 20}


def _rows(home: Path) -> list[sqlite3.Row]:
    database = home / "history.sqlite3"
    with sqlite3.connect(database) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute("SELECT * FROM runs ORDER BY rowid"))


def _reject(argv: list[str], capsys: pytest.CaptureFixture[str], home: Path) -> None:
    assert main(argv) == 2
    capsys.readouterr()
    assert not (home / "history.sqlite3").exists()


def test_clean_date_is_allow(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.splitlines() == ["ALLOW clean"]


def test_memory_poison_is_block(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", str(MEMORY)])

    captured = capsys.readouterr()
    assert code == 20
    assert len(captured.out.splitlines()) == 1
    assert captured.out.splitlines()[0].startswith("BLOCK high_finding ")
    assert captured.out.endswith("skill-memory-file-persistence\n")


def test_reader_medium_flag_is_ask(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("WARDEN_LLM_KEY", _KEY)

    def call(self: object, text: str) -> ReaderResult:
        return ReaderResult(["false_safety_claim"], ["reviewed"])

    monkeypatch.setattr("skill_warden.reader.Reader.call", call)

    code = main(
        [
            "scan",
            "--llm",
            "openai-compatible:fake",
            "--llm-key-env",
            "WARDEN_LLM_KEY",
            str(CLEAN),
        ]
    )

    captured = capsys.readouterr()
    assert code == 10
    assert captured.out.splitlines() == ["ASK medium_only false_safety_claim"]
    assert _KEY not in captured.out
    assert _KEY not in captured.err


def test_several_paths_exit_with_the_worst(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", str(MEMORY), str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 20
    lines = captured.out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"{MEMORY} BLOCK high_finding ")
    assert lines[0].endswith("skill-memory-file-persistence")
    assert lines[1] == f"{CLEAN} ALLOW clean"


def test_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--format", "json", str(MEMORY), str(CLEAN)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "skill-warden/scan@1"
    assert set(payload) == {"schema", "summary", "reports"}
    assert payload["summary"]["skills"] == 2
    assert payload["summary"]["counts"] == {"ALLOW": 1, "ASK": 0, "BLOCK": 1}
    assert payload["summary"]["worst"] == "BLOCK"
    assert _EXIT[payload["summary"]["worst"]] == code
    assert [item["skill"]["path"] for item in payload["reports"]] == [str(MEMORY), str(CLEAN)]
    assert [item["verdict"]["decision"] for item in payload["reports"]] == ["BLOCK", "ALLOW"]
    blocked = payload["reports"][0]
    assert blocked["verdict"]["reason"] == "high_finding"
    assert blocked["verdict"]["detail"].endswith("skill-memory-file-persistence")
    assert blocked["findings"]


def test_scan_inserts_one_history_row(history_home: Path) -> None:
    code = main(["scan", str(CLEAN)])

    assert code == 0
    rows = _rows(history_home)
    assert len(rows) == 1
    assert rows[0]["skill_path"] == str(CLEAN)
    assert rows[0]["decision"] == "ALLOW"
    assert rows[0]["reason"] == "clean"


def test_no_history_writes_nothing(history_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["scan", "--no-history", str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 0
    assert "ALLOW clean" in captured.out
    assert not (history_home / "history.sqlite3").exists()


def test_failed_history_write_keeps_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SKILL_WARDEN_HOME", str(blocker))

    code = main(["scan", str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == "history write failed\n"
    assert captured.out.splitlines() == ["ALLOW clean"]


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_env_key_never_appears(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    history_home: Path,
    fmt: str,
) -> None:
    monkeypatch.setenv("WARDEN_LLM_KEY", _KEY)
    monkeypatch.setenv("WARDEN_UNUSED_SECRET", _UNUSED)

    def call(self: object, text: str) -> ReaderResult:
        return ReaderResult(["false_safety_claim"], [f"send {_KEY} now"])

    monkeypatch.setattr("skill_warden.reader.Reader.call", call)

    code = main(
        [
            "scan",
            "--format",
            fmt,
            "--llm",
            "ollama:qwen2.5:7b",
            "--llm-base-url",
            "http://127.0.0.1:9/v1",
            "--llm-key-env",
            "WARDEN_LLM_KEY",
            str(CLEAN),
        ]
    )

    captured = capsys.readouterr()
    assert code == 10
    assert _KEY not in captured.out
    assert _KEY not in captured.err
    assert _UNUSED not in captured.out
    assert _UNUSED not in captured.err
    stored = (history_home / "history.sqlite3").read_bytes()
    assert _KEY.encode() not in stored
    assert _UNUSED.encode() not in stored
    if fmt == "json":
        assert json.loads(captured.out)["schema"] == "skill-warden/scan@1"


def test_bad_input_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    history_home: Path,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SKILL_WARDEN_MISSING_KEY", raising=False)
    missing = tmp_path / "missing-skill"
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("hello\n", encoding="utf-8")
    link = tmp_path / "linked-skill"
    link.symlink_to(CLEAN, target_is_directory=True)

    _reject(["scan"], capsys, history_home)
    _reject(["scan", "--format", "xml", str(CLEAN)], capsys, history_home)
    _reject(["scan", "--llm", "nomodel", str(CLEAN)], capsys, history_home)
    _reject(
        [
            "scan",
            "--llm",
            "openai-compatible:m",
            "--llm-key-env",
            "SKILL_WARDEN_MISSING_KEY",
            str(CLEAN),
        ],
        capsys,
        history_home,
    )
    _reject(["scan", str(missing)], capsys, history_home)
    _reject(["scan", str(skill_file)], capsys, history_home)
    _reject(["scan", str(link)], capsys, history_home)
    _reject(["scan", "--not-a-flag"], capsys, history_home)


def test_detonate_is_passed_to_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}

    def fake(
        paths: list[Path],
        *,
        llm: object = None,
        detonate: bool = False,
        history: bool = True,
        secrets: list[str] | None = None,
    ) -> tuple[Report, ...]:
        seen["paths"] = list(paths)
        seen["detonate"] = detonate
        seen["history"] = history
        seen["llm"] = llm
        return tuple(Report((), Verdict("ALLOW", "clean")) for _ in paths)

    monkeypatch.setattr("skill_warden.pipeline.scan", fake)

    code = main(["scan", "--detonate", "--no-history", str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 0
    assert seen["detonate"] is True
    assert seen["history"] is False
    assert seen["llm"] is None
    assert seen["paths"] == [CLEAN]
    assert captured.out.splitlines() == ["ALLOW clean"]


def test_unexpected_error_exits_1_without_the_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_args: object, **_kwargs: object) -> tuple[Report, ...]:
        raise RuntimeError(f"boom {_KEY}")

    monkeypatch.setattr("skill_warden.pipeline.scan", boom)

    code = main(["scan", str(CLEAN)])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == "scan failed\n"
    assert _KEY not in captured.out
    assert _KEY not in captured.err
