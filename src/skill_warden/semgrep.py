import json
import subprocess
from pathlib import Path


def scan(paths: list[Path], config: Path) -> dict:
    completed = subprocess.run(
        [
            "semgrep",
            "scan",
            "--metrics=off",
            "--json",
            "--scan-unknown-extensions",
            "--timeout",
            "20",
            "--config",
            str(config),
            *[str(path) for path in paths],
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return json.loads(completed.stdout)
