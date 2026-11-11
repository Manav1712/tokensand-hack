import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / "scripts" / "ci.py"
_PASSING_COVERAGE = json.dumps(
    {
        "totals": {"percent_covered": 90},
        "files": {
            "src/skill_warden/redact.py": {
                "missing_lines": [],
                "missing_branches": [],
                "summary": {
                    "percent_covered": 100,
                    "missing_branches": 0,
                    "num_partial_branches": 0,
                },
            },
            "src/skill_warden/hashing.py": {
                "missing_lines": [],
                "missing_branches": [],
                "summary": {
                    "percent_covered": 100,
                    "missing_branches": 0,
                    "num_partial_branches": 0,
                },
            },
            "src/skill_warden/policy.py": {
                "missing_lines": [],
                "missing_branches": [],
                "summary": {
                    "percent_covered": 100,
                    "missing_branches": 0,
                    "num_partial_branches": 0,
                },
            },
            "src/skill_warden/static/semgrep.py": {
                "missing_lines": [],
                "missing_branches": [],
                "summary": {
                    "percent_covered": 100,
                    "missing_branches": 0,
                    "num_partial_branches": 0,
                },
            },
        },
    }
)


def _load_ci():
    spec = importlib.util.spec_from_file_location("skill_warden_ci", CI_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(CI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Runner:
    def __init__(self, codes: Sequence[int] = ()) -> None:
        self.calls: list[list[str]] = []
        self._codes = list(codes)

    def __call__(self, argv: Sequence[str]) -> int:
        self.calls.append(list(argv))
        if "json" in argv:
            out = Path(argv[argv.index("-o") + 1])
            out.write_text(_PASSING_COVERAGE, encoding="utf-8")
        if not self._codes:
            return 0
        return self._codes.pop(0)


_TYPE_FILES = [
    "src/skill_warden/__init__.py",
    "src/skill_warden/cli.py",
    "src/skill_warden/errors.py",
    "src/skill_warden/frontmatter.py",
    "src/skill_warden/hashing.py",
    "src/skill_warden/history.py",
    "src/skill_warden/intake.py",
    "src/skill_warden/memory_store.py",
    "src/skill_warden/models.py",
    "src/skill_warden/paths.py",
    "src/skill_warden/pipeline.py",
    "src/skill_warden/policy.py",
    "src/skill_warden/redact.py",
    "src/skill_warden/static/semgrep.py",
]


def _expected(command: str) -> list[str]:
    py = sys.executable
    if command == "lint":
        return [py, "-m", "ruff", "check", "."]
    if command == "types":
        return [py, "-m", "mypy", "--strict", *_TYPE_FILES]
    if command == "imports":
        return [str(Path(py).with_name("lint-imports")), "--no-logo"]
    if command == "test":
        return [py, "-m", "pytest", "-q"]
    if command == "docker":
        return [py, "-m", "pytest", "-m", "docker", "-q"]
    raise AssertionError(command)


def test_lint_test_and_docker_argv():
    ci = _load_ci()
    for command in ("lint", "types", "imports", "test", "docker"):
        runner = _Runner()
        assert ci.main([command], runner) == 0
        assert runner.calls == [_expected(command)]


def _expected_coverage(ci) -> list[list[str]]:
    py = sys.executable
    return [
        [
            py,
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
            ci._coverage_mark(),
            "-q",
        ],
        [py, "-m", "coverage", "json", "-o", str(ROOT / "coverage.json")],
    ]


def test_pr_runs_lint_types_imports_then_coverage():
    ci = _load_ci()
    runner = _Runner()
    assert ci.main(["pr"], runner, changed_files=list) == 0
    assert runner.calls == [
        _expected("lint"),
        _expected("types"),
        _expected("imports"),
        *_expected_coverage(ci),
    ]


def test_pr_stops_when_lint_fails():
    ci = _load_ci()
    runner = _Runner([2])
    assert ci.main(["pr"], runner) == 2
    assert runner.calls == [_expected("lint")]


def test_pr_stops_when_types_fails():
    ci = _load_ci()
    runner = _Runner([0, 1])
    assert ci.main(["pr"], runner) == 1
    assert runner.calls == [_expected("lint"), _expected("types")]


def test_pr_stops_when_imports_fails():
    ci = _load_ci()
    runner = _Runner([0, 0, 1])
    assert ci.main(["pr"], runner) == 1
    assert runner.calls == [_expected("lint"), _expected("types"), _expected("imports")]


def test_pr_stops_when_coverage_fails():
    ci = _load_ci()
    runner = _Runner([0, 0, 0, 1])
    assert ci.main(["pr"], runner) == 1
    assert runner.calls == [
        _expected("lint"),
        _expected("types"),
        _expected("imports"),
        _expected_coverage(ci)[0],
    ]


def test_pr_stops_when_mutate_changed_fails(monkeypatch, tmp_path):
    ci = _load_ci()
    stats_path = tmp_path / "mutmut-cicd-stats.json"
    monkeypatch.setattr(ci, "MUTMUT_STATS", stats_path)
    runner = _Runner([0, 0, 0, 0, 0, 1])
    code = ci.main(
        ["pr"],
        runner,
        changed_files=lambda: ["src/skill_warden/redact.py"],
    )
    assert code == 1
    assert runner.calls[0] == _expected("lint")
    assert runner.calls[1] == _expected("types")
    assert runner.calls[2] == _expected("imports")
    assert runner.calls[3:5] == _expected_coverage(ci)
    assert runner.calls[5][:2] == ["mutmut", "run"]


def test_coverage_includes_case_collision_on_a_case_sensitive_disk():
    ci = _load_ci()
    mark = ci._coverage_mark()
    if ci._filesystem_is_case_sensitive():
        assert "not case_sensitive_fs" not in mark
    else:
        assert "not case_sensitive_fs" in mark


def test_unknown_command_does_not_run():
    ci = _load_ci()
    runner = _Runner()
    assert ci.main(["nope"], runner) == 2
    assert runner.calls == []
