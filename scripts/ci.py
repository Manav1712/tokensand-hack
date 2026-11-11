"""Run the local checks. The workflow calls ``pr`` and nothing else."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_JSON = ROOT / "coverage.json"
MUTMUT_STATS = ROOT / "mutants" / "mutmut-cicd-stats.json"
OVERALL_FLOOR = 90
CORE_MUTATION_FLOOR = 90
POLICY_MUTATION_FLOOR = 100

Runner = Callable[[Sequence[str]], int]
ChangedFiles = Callable[[], Sequence[str]]
_STEPS = ("lint", "test", "docker")
# Unit tests alone leave the Docker-only modules under the floor. Packaging
# and live-model tests stay out. Case-collision tests run when the disk can
# hold two names that differ only by case.
_CASE_SENSITIVE: bool | None = None


def _mypy_files() -> list[str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    files = config["tool"]["mypy"]["files"]
    if (
        not isinstance(files, list)
        or not files
        or not all(isinstance(item, str) and item for item in files)
    ):
        raise ValueError("tool.mypy.files must list the modules under strict checking")
    return files


def _argv(command: str) -> list[str]:
    python = sys.executable
    if command == "lint":
        return [python, "-m", "ruff", "check", "."]
    if command == "types":
        return [python, "-m", "mypy", "--strict", *_mypy_files()]
    if command == "imports":
        return [str(Path(python).with_name("lint-imports")), "--no-logo"]
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
            _coverage_mark(),
            "-q",
        ]
    raise ValueError(command)


def _filesystem_is_case_sensitive() -> bool:
    global _CASE_SENSITIVE
    if _CASE_SENSITIVE is not None:
        return _CASE_SENSITIVE
    sensitive = False
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "A").write_text("upper", encoding="utf-8")
            (root / "a").write_text("lower", encoding="utf-8")
            sensitive = (root / "A").read_text(encoding="utf-8") != (
                root / "a"
            ).read_text(encoding="utf-8")
    except OSError:
        sensitive = False
    _CASE_SENSITIVE = sensitive
    return sensitive


def _coverage_mark() -> str:
    mark = "not live_llm and not packaging"
    if not _filesystem_is_case_sensitive():
        mark += " and not case_sensitive_fs"
    return mark


def _coverage_json_argv() -> list[str]:
    return [sys.executable, "-m", "coverage", "json", "-o", str(COVERAGE_JSON)]


def _run_step(command: str, runner: Runner) -> int:
    return runner(_argv(command))


def _run_types(runner: Runner) -> int:
    try:
        argv = _argv("types")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"types: {exc}", file=sys.stderr)
        return 1
    return runner(argv)


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


def mutation_floor(path: str) -> float:
    normalized = path.replace("\\", "/")
    if normalized.endswith("policy.py"):
        return float(POLICY_MUTATION_FLOOR)
    return float(CORE_MUTATION_FLOOR)


def _kill_rate(stats: Mapping[str, object]) -> float | None:
    def count(key: str) -> int:
        value = stats.get(key, 0)
        return value if isinstance(value, int) else 0

    killed = count("killed")
    denominator = (
        killed
        + count("survived")
        + count("timeout")
        + count("suspicious")
        + count("no_tests")
    )
    if denominator == 0:
        return None
    return 100.0 * killed / denominator


def mutation_problems(
    report: Mapping[str, Mapping[str, object]],
    paths: Sequence[str],
) -> list[str]:
    """Return why these mutation stats miss the floor. Empty means they pass."""
    problems: list[str] = []
    for path in paths:
        entry = report.get(path)
        if entry is None:
            problems.append(f"{path} is missing from the mutation report")
            continue
        rate = _kill_rate(entry)
        floor = mutation_floor(path)
        if rate is None:
            problems.append(f"{path} produced no mutants")
            continue
        if rate < floor:
            problems.append(f"{path} kill rate {rate:g} is below {floor:g}")
    return problems


def _mutant_pattern(path: str) -> str:
    relative = Path(path.replace("\\", "/"))
    module = relative.with_suffix("").as_posix().removeprefix("src/")
    return module.replace("/", ".") + "*"


def _status_by_exit_code(code: object) -> str:
    mapping = {
        1: "killed",
        3: "killed",
        0: "survived",
        5: "no_tests",
        33: "no_tests",
        35: "suspicious",
        36: "timeout",
        255: "timeout",
        24: "timeout",
        -24: "timeout",
        152: "timeout",
    }
    if isinstance(code, int) and code in mapping:
        return mapping[code]
    if code is None:
        return "not_checked"
    return "suspicious"


def _stats_from_meta(meta_path: Path) -> dict[str, int]:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    exit_codes = meta.get("exit_code_by_key") or {}
    stats = {
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "suspicious": 0,
        "no_tests": 0,
    }
    survivors: list[str] = []
    for key, code in exit_codes.items():
        status = _status_by_exit_code(code)
        if status == "survived":
            survivors.append(key)
        if status in stats:
            stats[status] += 1
    if survivors:
        print("mutate survivors:", file=sys.stderr)
        for name in survivors:
            print(f"  {name}", file=sys.stderr)
    return stats


def _stats_for_path(path: str) -> Mapping[str, object]:
    meta_path = ROOT / "mutants" / f"{path}.meta"
    if meta_path.is_file():
        return _stats_from_meta(meta_path)
    return json.loads(MUTMUT_STATS.read_text(encoding="utf-8"))


def _git_output(args: Sequence[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git failed")
    return [line for line in result.stdout.splitlines() if line]


_BASE_REFS = ("origin/main", "main")


def _base_ref() -> str:
    errors: list[str] = []
    for name in _BASE_REFS:
        try:
            _git_output(["rev-parse", "--verify", name])
        except RuntimeError as exc:
            errors.append(f"{name}: {exc}")
            continue
        return name
    detail = "; ".join(errors)
    raise RuntimeError(
        "mutate --changed could not find origin/main or main"
        + (f" ({detail})" if detail else "")
    )


def _changed_since_base() -> tuple[str, list[str]]:
    base = _base_ref()
    try:
        merge_base = _git_output(["merge-base", base, "HEAD"])
    except RuntimeError as exc:
        raise RuntimeError(
            f"mutate --changed could not find a merge-base of {base} and HEAD: {exc}"
        ) from exc
    if not merge_base:
        raise RuntimeError(
            f"mutate --changed could not find a merge-base of {base} and HEAD"
        )
    names = set(_git_output(["diff", "--name-only", f"{merge_base[0]}...HEAD"]))
    names.update(_git_output(["diff", "--name-only"]))
    names.update(_git_output(["diff", "--name-only", "--cached"]))
    return base, sorted(names)


def _default_changed_files() -> list[str]:
    return _changed_since_base()[1]


def _run_mutate(
    runner: Runner,
    *,
    changed_only: bool,
    changed_files: ChangedFiles | None,
) -> int:
    try:
        core = _core_files()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"mutate: {exc}", file=sys.stderr)
        return 1
    if changed_only:
        base: str | None = None
        try:
            if changed_files is None:
                base, names = _changed_since_base()
                changed = set(names)
            else:
                changed = set(changed_files())
        except RuntimeError as exc:
            print(f"mutate: {exc}", file=sys.stderr)
            return 1
        targets = [path for path in core if path in changed]
        if base is not None:
            listed = ", ".join(targets) if targets else "no core files"
            print(f"mutate --changed: base {base}, {listed}", file=sys.stderr)
        if not targets:
            return 0
    else:
        targets = list(core)

    report: dict[str, Mapping[str, object]] = {}
    for path in targets:
        code = runner(["mutmut", "run", _mutant_pattern(path)])
        if code != 0:
            return code
        code = runner(["mutmut", "export-cicd-stats"])
        if code != 0:
            return code
        try:
            report[path] = _stats_for_path(path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"mutate: {path}: {exc}", file=sys.stderr)
            return 1

    problems = mutation_problems(report, targets)
    for problem in problems:
        print(f"mutate: {problem}", file=sys.stderr)
    return 1 if problems else 0


def _pr(runner: Runner, changed_files: ChangedFiles | None) -> int:
    code = _run_step("lint", runner)
    if code != 0:
        return code
    code = _run_types(runner)
    if code != 0:
        return code
    code = _run_step("imports", runner)
    if code != 0:
        return code
    code = _run_coverage(runner)
    if code != 0:
        return code
    return _run_mutate(runner, changed_only=True, changed_files=changed_files)


def main(
    argv: Sequence[str] | None = None,
    runner: Runner | None = None,
    changed_files: ChangedFiles | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if runner is None:

        def runner(command: Sequence[str]) -> int:
            return subprocess.call(list(command), cwd=ROOT)

    if not args:
        print(
            "usage: python scripts/ci.py "
            "{lint,types,imports,test,coverage,mutate,docker,pr}",
            file=sys.stderr,
        )
        return 2

    command = args[0]
    rest = args[1:]
    known = {*_STEPS, "types", "imports", "coverage", "mutate", "pr"}
    if command not in known:
        print(
            "usage: python scripts/ci.py "
            "{lint,types,imports,test,coverage,mutate,docker,pr}",
            file=sys.stderr,
        )
        return 2

    if command == "pr":
        if rest:
            print("usage: python scripts/ci.py pr", file=sys.stderr)
            return 2
        return _pr(runner, changed_files)

    if command == "types":
        if rest:
            print("usage: python scripts/ci.py types", file=sys.stderr)
            return 2
        return _run_types(runner)

    if command == "coverage":
        if rest:
            print("usage: python scripts/ci.py coverage", file=sys.stderr)
            return 2
        return _run_coverage(runner)

    if command == "mutate":
        changed_only = False
        if rest == ["--changed"]:
            changed_only = True
        elif rest:
            print(
                "usage: python scripts/ci.py mutate [--changed]",
                file=sys.stderr,
            )
            return 2
        return _run_mutate(
            runner,
            changed_only=changed_only,
            changed_files=changed_files,
        )

    if rest:
        print(
            f"usage: python scripts/ci.py {command}",
            file=sys.stderr,
        )
        return 2
    return _run_step(command, runner)


if __name__ == "__main__":
    raise SystemExit(main())
