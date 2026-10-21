"""Run the local checks. The workflow calls ``pr`` and nothing else."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

Runner = Callable[[Sequence[str]], int]
_STEPS = ("lint", "test", "docker")


def _argv(command: str) -> list[str]:
    python = sys.executable
    if command == "lint":
        return [python, "-m", "ruff", "check", "."]
    if command == "test":
        return [python, "-m", "pytest", "-q"]
    if command == "docker":
        return [python, "-m", "pytest", "-m", "docker", "-q"]
    raise ValueError(command)


def _run_step(command: str, runner: Runner) -> int:
    return runner(_argv(command))


def _pr(runner: Runner) -> int:
    for command in _STEPS:
        code = _run_step(command, runner)
        if code != 0:
            return code
    return 0


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if runner is None:

        def runner(command: Sequence[str]) -> int:
            return subprocess.call(list(command), cwd=ROOT)

    if len(args) != 1 or args[0] not in {*_STEPS, "pr"}:
        print(
            "usage: python scripts/ci.py {lint,test,docker,pr}",
            file=sys.stderr,
        )
        return 2
    if args[0] == "pr":
        return _pr(runner)
    return _run_step(args[0], runner)


if __name__ == "__main__":
    raise SystemExit(main())
