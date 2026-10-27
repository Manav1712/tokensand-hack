"""The skill-warden command line."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from skill_warden.models import Report
from skill_warden.pipeline import scan
from skill_warden.reader import Reader
from skill_warden.redact import redact

_EXIT = {"ALLOW": 0, "ASK": 10, "BLOCK": 20}
_SECRET_PARTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
_USAGE = (
    "usage: skill-warden scan PATH [PATH ...] "
    "[--llm PROVIDER:MODEL --llm-base-url URL --llm-key-env VAR] "
    "[--detonate] [--format text|json] [--no-history]"
)


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _Usage(message)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
        paths = _directories(args.paths)
        llm = _reader(args.llm, args.llm_base_url, args.llm_key_env)
    except _Usage as exc:
        message = redact(str(exc), _secrets())
        print(_USAGE, file=sys.stderr)
        print(f"skill-warden: {message}", file=sys.stderr)
        return 2
    reports = scan(
        paths,
        llm=llm,
        detonate=args.detonate,
        history=not args.no_history,
    )
    rendered = redact(_render(args.format, paths, reports), _secrets())
    sys.stdout.write(rendered)
    return _exit_code(reports)


def _parser() -> _Parser:
    parser = _Parser(prog="skill-warden")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    scan_command = commands.add_parser("scan")
    scan_command.add_argument("paths", nargs="+")
    scan_command.add_argument("--llm")
    scan_command.add_argument("--llm-base-url")
    scan_command.add_argument("--llm-key-env")
    scan_command.add_argument("--detonate", action="store_true")
    scan_command.add_argument("--format", choices=("text", "json"), default="text")
    scan_command.add_argument("--no-history", action="store_true")
    return parser


def _directories(items: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    for item in items:
        path = Path(item)
        if path.is_symlink() or not path.is_dir():
            raise _Usage(f"not a skill directory: {item}")
        paths.append(path)
    return paths


def _reader(llm: str | None, base_url: str | None, key_env: str | None) -> Reader | None:
    if llm is None:
        return None
    _provider, separator, model = llm.partition(":")
    if not separator or not _provider or not model:
        raise _Usage("--llm must be PROVIDER:MODEL")
    if not base_url:
        raise _Usage("--llm-base-url is required with --llm")
    if not key_env:
        raise _Usage("--llm-key-env is required with --llm")
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise _Usage(f"{key_env} is not set")
    return Reader(api_key=api_key, base_url=base_url, model=model)


def _render(fmt: str, paths: Sequence[Path], reports: Sequence[Report]) -> str:
    if fmt == "json":
        return json.dumps(_envelope(paths, reports), indent=2) + "\n"
    lines = []
    show_path = len(paths) > 1
    for path, report in zip(paths, reports, strict=True):
        verdict = report.verdict
        parts = [verdict.decision, verdict.reason]
        if verdict.detail:
            parts.append(verdict.detail)
        if show_path:
            parts.append(str(path))
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def _envelope(paths: Sequence[Path], reports: Sequence[Report]) -> dict[str, object]:
    counts = {"BLOCK": 0, "ASK": 0, "ALLOW": 0}
    for report in reports:
        counts[report.verdict.decision] += 1
    worst = next(decision for decision in ("BLOCK", "ASK", "ALLOW") if counts[decision])
    return {
        "schema": "skill-warden/scan@1",
        "summary": {"skills": len(reports), "worst": worst, "counts": counts},
        "reports": [
            {
                "skill": {"path": str(path)},
                "verdict": {
                    "decision": report.verdict.decision,
                    "reason": report.verdict.reason,
                    "detail": report.verdict.detail,
                },
                "findings": [finding.to_row() for finding in report.findings],
            }
            for path, report in zip(paths, reports, strict=True)
        ],
    }


def _exit_code(reports: Sequence[Report]) -> int:
    return max(_EXIT[report.verdict.decision] for report in reports)


def _secrets() -> list[str]:
    found = [
        value
        for name, value in os.environ.items()
        if any(part in name.upper() for part in _SECRET_PARTS)
    ]
    return sorted(found, key=len, reverse=True)


if __name__ == "__main__":
    raise SystemExit(main())
