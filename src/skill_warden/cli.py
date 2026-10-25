from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from skill_warden import pipeline
from skill_warden.models import Report
from skill_warden.reader import Reader
from skill_warden.redact import redact

_EXIT = {"ALLOW": 0, "ASK": 10, "BLOCK": 20}
_RANK = {"ALLOW": 0, "ASK": 1, "BLOCK": 2}
_FAILED = "scan failed"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _main(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as exc:
        return _status(exc.code)
    except Exception:  # noqa: BLE001
        print(_FAILED, file=sys.stderr)
        return 1


def _status(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 2


def _main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    secrets, reader, error = _reader(args)
    if error is not None:
        print(redact(error, secrets), file=sys.stderr)
        return 2
    paths = [Path(path) for path in args.paths]
    for path in paths:
        if path.is_symlink() or not path.is_dir():
            print(redact(f"error: not a directory: {path}", secrets), file=sys.stderr)
            return 2
    reports = pipeline.scan(
        paths,
        llm=reader,
        detonate=args.detonate,
        history=not args.no_history,
        secrets=secrets,
    )
    print(redact(_render(paths, reports, args.format), secrets))
    return _EXIT[_worst(reports)]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill-warden")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("paths", nargs="+", type=Path)
    scan.add_argument("--llm")
    scan.add_argument("--llm-base-url")
    scan.add_argument("--llm-key-env")
    scan.add_argument("--detonate", action="store_true")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument("--no-history", action="store_true")
    return parser


def _reader(args: argparse.Namespace) -> tuple[list[str], Reader | None, str | None]:
    secrets: list[str] = []
    key = ""
    if args.llm_key_env is not None:
        if args.llm_key_env not in os.environ:
            return secrets, None, f"error: {args.llm_key_env} is unset"
        key = os.environ[args.llm_key_env]
        if len(key) > 3:
            secrets.append(key)
    if args.llm is None:
        return secrets, None, None
    if ":" not in args.llm:
        return secrets, None, "error: --llm must be PROVIDER:MODEL"
    model = args.llm.split(":", 1)[1]
    options = {"api_key": key, "model": model}
    if args.llm_base_url:
        options["base_url"] = args.llm_base_url
    return secrets, Reader(**options), None


def _render(paths: Sequence[Path], reports: Sequence[Report], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(_envelope(paths, reports), indent=2, sort_keys=True)
    show_path = len(paths) > 1
    lines = [
        _line(path, report, show_path=show_path)
        for path, report in zip(paths, reports, strict=True)
    ]
    return "\n".join(lines)


def _line(path: Path, report: Report, *, show_path: bool) -> str:
    verdict = report.verdict
    line = f"{verdict.decision} {verdict.reason}"
    if verdict.detail:
        line = f"{line} {verdict.detail}"
    if show_path:
        return f"{path} {line}"
    return line


def _envelope(paths: Sequence[Path], reports: Sequence[Report]) -> dict[str, object]:
    counts = {"ALLOW": 0, "ASK": 0, "BLOCK": 0}
    for report in reports:
        counts[report.verdict.decision] += 1
    return {
        "schema": "skill-warden/scan@1",
        "summary": {"skills": len(reports), "worst": _worst(reports), "counts": counts},
        "reports": [
            {
                "skill": {"path": os.fspath(path)},
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


def _worst(reports: Sequence[Report]) -> str:
    return max((report.verdict.decision for report in reports), key=_RANK.__getitem__)


if __name__ == "__main__":
    raise SystemExit(main())
