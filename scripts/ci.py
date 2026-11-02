"""Run the local checks. The workflow calls ``pr`` and nothing else."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_JSON = ROOT / "coverage.json"
OVERALL_FLOOR = 90

Runner = Callable[[Sequence[str]], int]
_STEPS = ("lint", "test", "docker")
# Unit tests alone leave the Docker-only modules under the floor. Packaging
# and live-model tests stay out.
_COVERAGE_MARK = "not live_llm and not packaging and not case_sensitive_fs"


def _argv(command: str) -> list[str]:
    python = sys.executable
    if command == "lint":
        return [python, "-m", "ruff", "check", "."]
    if command == "test":
        return [python, "-m", "pytest", "-q"]
    if command == "docker":
        return [python, "-m", "pytest", "-m", "docker", "-q"]
    if command == "coverage":
        return [
            python,
            "-m",
            "coverage",
            "run",
            "--source=src/skill_warden",
            "--branch",
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-m",
            _COVERAGE_MARK,
            "-q",
        ]
    raise ValueError(command)


def _coverage_json_argv() -> list[str]:
    return [sys.executable, "-m", "coverage", "json", "-o", str(COVERAGE_JSON)]


def _run_step(command: str, runner: Runner) -> int:
    return runner(_argv(command))


def _core_files() -> list[str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    files = config["tool"]["skill_warden"]["core"]["files"]
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(item, str) and item for item in files)
    ):
        raise ValueError("tool.skill_warden.core.files must list the core paths")
    return files


def _find_entry(files: Mapping[str, object], wanted: str) -> object | None:
    if wanted in files:
        return files[wanted]
    suffix = "/" + wanted.replace("\\", "/")
    for key, value in files.items():
        if key.replace("\\", "/").endswith(suffix):
            return value
    return None


def _file_problems(path: str, entry: object) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{path} is missing from the coverage report"]
    problems: list[str] = []
    missing_lines = entry.get("missing_lines") or []
    if missing_lines:
        listed = ", ".join(str(line) for line in missing_lines)
        problems.append(f"{path} uncovered lines: {listed}")
    missing_branches = entry.get("missing_branches") or []
    summary = entry.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    partial = summary.get("num_partial_branches") or 0
    summary_missing = summary.get("missing_branches") or 0
    if missing_branches or partial or summary_missing:
        problems.append(f"{path} uncovered branches")
    percent = summary.get("percent_covered", 0)
    if isinstance(percent, (int, float)) and percent < 100 and not problems:
        problems.append(f"{path} coverage {percent:g} is below 100")
    return problems


def coverage_problems(
    report: Mapping[str, object],
    core: Sequence[str],
    *,
    floor: float = OVERALL_FLOOR,
) -> list[str]:
    """Return why this coverage report misses the floor. Empty means it passes."""
    problems: list[str] = []
    totals = report.get("totals")
    percent = totals.get("percent_covered") if isinstance(totals, dict) else None
    if not isinstance(percent, (int, float)) or percent < floor:
        shown = percent if isinstance(percent, (int, float)) else "missing"
        problems.append(f"overall coverage {shown} is below {floor:g}")
    files = report.get("files")
    if not isinstance(files, dict):
        problems.append("coverage report has no files")
        return problems
    for path in core:
        entry = _find_entry(files, path)
        if entry is None:
            problems.append(f"{path} is missing from the coverage report")
            continue
        problems.extend(_file_problems(path, entry))
    return problems


def _check_coverage(path: Path) -> int:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        core = _core_files()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"coverage: {exc}", file=sys.stderr)
        return 1
    problems = coverage_problems(report, core)
    for problem in problems:
        print(f"coverage: {problem}", file=sys.stderr)
    return 1 if problems else 0


def _run_coverage(runner: Runner) -> int:
    previous = os.environ.get("HYPOTHESIS_PROFILE")
    os.environ["HYPOTHESIS_PROFILE"] = "ci"
    try:
        code = runner(_argv("coverage"))
        if code == 0:
            code = runner(_coverage_json_argv())
    finally:
        if previous is None:
            os.environ.pop("HYPOTHESIS_PROFILE", None)
        else:
            os.environ["HYPOTHESIS_PROFILE"] = previous
    if code != 0:
        return code
    return _check_coverage(COVERAGE_JSON)


def _pr(runner: Runner) -> int:
    code = _run_step("lint", runner)
    if code != 0:
        return code
    return _run_coverage(runner)


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if runner is None:

        def runner(command: Sequence[str]) -> int:
            return subprocess.call(list(command), cwd=ROOT)

    if len(args) != 1 or args[0] not in {*_STEPS, "coverage", "pr"}:
        print(
            "usage: python scripts/ci.py {lint,test,coverage,docker,pr}",
            file=sys.stderr,
        )
        return 2
    if args[0] == "pr":
        return _pr(runner)
    if args[0] == "coverage":
        return _run_coverage(runner)
    return _run_step(args[0], runner)


if __name__ == "__main__":
    raise SystemExit(main())
