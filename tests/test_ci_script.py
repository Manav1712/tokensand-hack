import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / "scripts" / "ci.py"


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
        if not self._codes:
            return 0
        return self._codes.pop(0)


def _expected(command: str) -> list[str]:
    py = sys.executable
    if command == "lint":
        return [py, "-m", "ruff", "check", "."]
    if command == "test":
        return [py, "-m", "pytest", "-q"]
    if command == "docker":
        return [py, "-m", "pytest", "-m", "docker", "-q"]
    raise AssertionError(command)


def test_lint_test_and_docker_argv():
    ci = _load_ci()
    for command in ("lint", "test", "docker"):
        runner = _Runner()
        assert ci.main([command], runner) == 0
        assert runner.calls == [_expected(command)]


def test_pr_runs_lint_test_docker_in_order():
    ci = _load_ci()
    runner = _Runner()
    assert ci.main(["pr"], runner) == 0
    assert runner.calls == [
        _expected("lint"),
        _expected("test"),
        _expected("docker"),
    ]


def test_pr_stops_when_lint_fails():
    ci = _load_ci()
    runner = _Runner([2])
    assert ci.main(["pr"], runner) == 2
    assert runner.calls == [_expected("lint")]


def test_pr_stops_when_test_fails():
    ci = _load_ci()
    runner = _Runner([0, 1])
    assert ci.main(["pr"], runner) == 1
    assert runner.calls == [_expected("lint"), _expected("test")]


def test_unknown_command_does_not_run():
    ci = _load_ci()
    runner = _Runner()
    assert ci.main(["nope"], runner) == 2
    assert runner.calls == []
