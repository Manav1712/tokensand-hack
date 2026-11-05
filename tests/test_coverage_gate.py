import importlib.util
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / "scripts" / "ci.py"
CORE = [
    "src/skill_warden/redact.py",
    "src/skill_warden/hashing.py",
    "src/skill_warden/policy.py",
]


def _load_ci():
    spec = importlib.util.spec_from_file_location("skill_warden_ci_coverage", CI_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(CI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file(missing_lines=None, missing_branches=None, percent=100):
    missing_lines = [] if missing_lines is None else missing_lines
    missing_branches = [] if missing_branches is None else missing_branches
    return {
        "missing_lines": missing_lines,
        "missing_branches": missing_branches,
        "summary": {
            "percent_covered": percent,
            "missing_branches": len(missing_branches),
            "num_partial_branches": len(missing_branches),
        },
    }


def _report(percent, files):
    return {"totals": {"percent_covered": percent}, "files": files}


def _covered():
    return _report(90, {path: _file() for path in CORE})


def test_gate_fails_when_a_core_line_is_uncovered():
    ci = _load_ci()
    files = {path: _file() for path in CORE}
    files[CORE[0]] = _file(missing_lines=[8])

    problems = ci.coverage_problems(_report(95, files), CORE)

    assert problems
    assert any("redact.py" in problem and "8" in problem for problem in problems)


def test_gate_fails_when_a_core_branch_is_uncovered():
    ci = _load_ci()
    files = {path: _file() for path in CORE}
    files[CORE[1]] = _file(missing_branches=[[16, 17]], percent=97)

    problems = ci.coverage_problems(_report(95, files), CORE)

    assert any("hashing.py" in problem for problem in problems)


def test_gate_fails_when_overall_coverage_is_below_90():
    ci = _load_ci()

    problems = ci.coverage_problems(_report(89.9, {path: _file() for path in CORE}), CORE)

    assert any("90" in problem for problem in problems)


def test_gate_fails_when_a_core_file_was_not_measured():
    ci = _load_ci()
    files = {CORE[0]: _file()}

    problems = ci.coverage_problems(_report(100, files), CORE)

    assert any("hashing.py" in problem and "missing" in problem for problem in problems)


def test_gate_passes_at_the_floor_when_core_files_are_covered():
    ci = _load_ci()

    assert ci.coverage_problems(_covered(), CORE) == []


def test_coverage_command_uses_ci_profile_and_checks_the_report(tmp_path, monkeypatch):
    ci = _load_ci()
    report_path = tmp_path / "coverage.json"
    monkeypatch.setattr(ci, "COVERAGE_JSON", report_path)
    calls: list[list[str]] = []
    seen: list[str | None] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(list(argv))
        seen.append(os.environ.get("HYPOTHESIS_PROFILE"))
        if "json" in argv:
            report_path.write_text(json.dumps(_covered()), encoding="utf-8")
        return 0

    monkeypatch.delenv("HYPOTHESIS_PROFILE", raising=False)
    assert ci.main(["coverage"], runner) == 0
    assert seen == ["ci", "ci"]
    assert os.environ.get("HYPOTHESIS_PROFILE") is None
    assert calls[0][:3] == [sys.executable, "-m", "coverage"]
    assert "run" in calls[0]
    assert "--branch" in calls[0]
    assert "--source=src/skill_warden" in calls[0]
    assert "not live_llm and not packaging and not case_sensitive_fs" in calls[0]
    assert calls[1][:4] == [sys.executable, "-m", "coverage", "json"]


def test_coverage_command_fails_when_the_report_has_an_uncovered_core_line(tmp_path, monkeypatch):
    ci = _load_ci()
    report_path = tmp_path / "coverage.json"
    monkeypatch.setattr(ci, "COVERAGE_JSON", report_path)
    files = {path: _file() for path in CORE}
    files[CORE[0]] = _file(missing_lines=[8])

    def runner(argv: Sequence[str]) -> int:
        if "json" in argv:
            report_path.write_text(
                json.dumps(_report(95, files)),
                encoding="utf-8",
            )
        return 0

    code = ci.main(["coverage"], runner)

    assert code == 1
