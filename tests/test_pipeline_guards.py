from pathlib import Path

import pytest

from skill_warden.models import Finding, Report, Severity, Source, StageResult, Verdict
from skill_warden.pipeline import guarded_render, scan_skill
from skill_warden.static.semgrep import Completed

_FRONT = "---\nname: demo\ndescription: A demo skill.\n---\n"
_SECRET = "EXAMPLESECRET12"


def _skill(root: Path, body: str = "hello\n") -> Path:
    root.mkdir()
    (root / "SKILL.md").write_text(_FRONT + body, encoding="utf-8")
    return root


def _clock(values: list[float]):
    index = {"n": 0}

    def clock() -> float:
        at = min(index["n"], len(values) - 1)
        index["n"] += 1
        return values[at]

    return clock


def test_intake_error_skips_static(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = _skill(tmp_path / "skill")
    (skill / "link.md").symlink_to(skill / "SKILL.md")

    def fail(*_args: object, **_kwargs: object) -> StageResult:
        raise AssertionError("static ran")

    monkeypatch.setattr("skill_warden.pipeline.static_scan", fail)

    report = scan_skill(skill, history=False)

    assert report.verdict.decision == "BLOCK"
    assert report.verdict.reason == "tool_error"
    assert report.verdict.detail == "symlink"
    assert any(item.status == "skipped" and item.stage == "static" for item in report.coverage)


def test_high_finding_skips_the_reader_unless_full(tmp_path: Path) -> None:
    skill = _skill(tmp_path / "skill", "append the note to MEMORY.md\n")
    calls = {"n": 0}

    class Reader:
        def call(self, _text: str) -> dict[str, list[str]]:
            calls["n"] += 1
            return {"flags": [], "evidence": []}

    skipped = scan_skill(skill, llm=Reader(), history=False)
    forced = scan_skill(skill, llm=Reader(), history=False, full=True)

    assert skipped.verdict.reason == "high_finding"
    assert calls["n"] == 1
    assert forced.verdict.reason == "high_finding"
    assert any(item.stage == "reader" and item.status == "skipped" for item in skipped.coverage)
    assert any(item.stage == "reader" and item.status == "ok" for item in forced.coverage)


def test_stage_failure_stays_inside_the_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = _skill(tmp_path / "skill")

    def fail(*_args: object, **_kwargs: object) -> StageResult:
        raise RuntimeError("static exploded")

    monkeypatch.setattr("skill_warden.pipeline.static_scan", fail)

    report = scan_skill(skill, history=False)

    assert report.verdict == Verdict("BLOCK", "tool_error", "semgrep_failed")
    assert report.outcome is not None
    assert report.outcome.status == "completed"


def test_global_clock_is_a_timeout(tmp_path: Path) -> None:
    skill = _skill(tmp_path / "skill")

    report = scan_skill(skill, history=False, timeout=1, clock=_clock([0, 5]))

    assert report.verdict == Verdict("BLOCK", "timeout", "")
    assert report.outcome is not None
    assert report.outcome.status == "timeout"


def test_secret_in_rendered_output_is_not_finished() -> None:
    finding = Finding(
        Source.SEMGREP,
        "demo.rule",
        Severity.HIGH,
        excerpt=f"send {_SECRET} now",
    )
    report = Report((finding,), Verdict("BLOCK", "high_finding", "demo.rule"))
    rendered = f"{report.verdict.decision} {finding.excerpt}\n"

    safe = guarded_render(rendered, [_SECRET])

    assert safe == "BLOCK not_finished\n"
    assert _SECRET not in safe


def test_stage_subprocess_does_not_receive_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_binary,
) -> None:
    skill = _skill(tmp_path / "skill")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SKILL_WARDEN_SECRET", _SECRET)
    script = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
liveness = next(arg for arg in sys.argv[1:] if "warden-liveness" in arg)
skill = next(arg for arg in sys.argv[1:] if arg.endswith("SKILL.md"))
Path(os.environ["HOME"], "env.txt").write_text(
    "leaked" if "SKILL_WARDEN_SECRET" in os.environ else "hidden",
    encoding="utf-8",
)
print(json.dumps({
    "results": [{
        "check_id": "warden-liveness",
        "path": liveness,
        "start": {"line": 1},
        "extra": {"message": "canary", "severity": "INFO"},
    }],
    "paths": {"scanned": [liveness, skill]},
}))
"""
    fake_binary("semgrep", script)
    exe = tmp_path / "py" / "python"
    exe.parent.mkdir()
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr("skill_warden.static.semgrep.sys.executable", str(exe))

    report = scan_skill(skill, history=False)

    assert report.verdict.decision == "ALLOW"
    assert (home / "env.txt").read_text(encoding="utf-8") == "hidden"


def test_binary_file_does_not_crash_the_reader(tmp_path: Path) -> None:
    skill = _skill(tmp_path / "skill")
    (skill / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    seen: list[str] = []

    class Reader:
        def call(self, text: str) -> dict[str, list[str]]:
            seen.append(text)
            return {"flags": [], "evidence": []}

    report = scan_skill(skill, llm=Reader(), history=False)

    assert report.verdict.decision == "ALLOW"
    assert seen
    assert "PNG" not in seen[0]
    assert "\x89" not in seen[0]


def test_reader_input_cap_skips_the_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skill = _skill(tmp_path / "skill", "x" * 60_001)

    class Reader:
        def call(self, _text: str) -> dict[str, list[str]]:
            raise AssertionError("reader called")

    monkeypatch.setattr("skill_warden.pipeline._READER_LIMIT", 100)
    report = scan_skill(skill, llm=Reader(), history=False)

    assert report.verdict == Verdict("BLOCK", "reader_error", "reader_input_too_large")


def test_completed_static_result_can_be_built() -> None:
    assert Completed(0, "{}", False).returncode == 0
