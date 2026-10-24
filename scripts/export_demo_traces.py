"""Export demo traces from real Skill Warden runs.

Needs the local ClickHouse test container on port 18123 and semgrep on PATH.
Viewers of the demo never run this. The nonce below must stay out of the JSON.
"""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import clickhouse_connect

from skill_warden.breaker import Breaker
from skill_warden.findings import build_rows
from skill_warden.hashing import content_hash
from skill_warden.honeytoken import build_home, search_nonce
from skill_warden.jail import JAIL_IMAGE, plan
from skill_warden.orchestrator import Orchestrator
from skill_warden.registry import SkillRecord
from skill_warden.semgrep import rule_path
from skill_warden.semgrep import scan as semgrep_scan
from skill_warden.sink import SINK_IP
from skill_warden.store import Store
from skill_warden.verdict import load_sql

SKILLS = ROOT / "fixtures" / "skills"
RULES = rule_path()
OUT = ROOT / "demo" / "src" / "data" / "traces.json"
NONCE = "FAKE-CANARY-NONCE-DEMO"

EXPECTED = {
    "clean-date": ("ALLOW", "clean"),
    "memory-poison": ("BLOCK", "high_finding"),
    "audited-exfil": ("BLOCK", "high_finding"),
    "prose-exfil": ("BLOCK", "high_finding"),
}
READER_FLAGS = {
    "clean-date": [],
    "memory-poison": [],
    "audited-exfil": ["false_safety_claim"],
    "prose-exfil": ["credential_exfil"],
}
READER_EVIDENCE = {
    "audited-exfil": ["security-audited"],
    "prose-exfil": ["api keys"],
}


class ScriptedReader:
    def __init__(self, flags: list[str], evidence: list[str]) -> None:
        self._body = {"flags": flags, "evidence": evidence}

    def call(self, _text: str) -> dict:
        return self._body


class RecordingStore(Store):
    def __init__(self, client) -> None:
        super().__init__(client)
        self.last_run_id: UUID | None = None

    def insert_run(
        self,
        run_id: UUID,
        skill_hash: str,
        *,
        backend: str = "local",
        budget_cents: int = 0,
    ) -> None:
        self.last_run_id = run_id
        super().insert_run(run_id, skill_hash, backend=backend, budget_cents=budget_cents)


def connect():
    try:
        client = clickhouse_connect.get_client(
            host="localhost",
            port=18123,
            username="scanner",
            password="test",
            database="skill_warden",
            secure=False,
        )
        client.query("SELECT 1")
        return client
    except Exception as exc:
        raise SystemExit(
            "ClickHouse is not reachable at localhost:18123 "
            "(user scanner, database skill_warden). "
            "Start the skill-warden-ch-test container and apply schema/001_init.sql.\n"
            f"{exc}"
        ) from exc


def skill_files(root: Path) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if name == "HASH" or path.is_symlink() or not path.is_file():
                continue
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "text": path.read_text(encoding="utf-8"),
                }
            )
    return sorted(files, key=lambda item: item["path"])


def relativize(path: str, root: Path) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path


def semgrep_hits(report: dict, root: Path) -> list[dict]:
    hits: list[dict] = []
    for result in report.get("results") or []:
        extra = result.get("extra") or {}
        start = result.get("start") or {}
        hits.append(
            {
                "ruleId": str(result.get("check_id") or ""),
                "path": relativize(str(result.get("path") or ""), root),
                "startLine": int(start.get("line") or 0),
                "severity": str(extra.get("severity") or ""),
            }
        )
    return hits


def finding_rows(client, run_id: UUID, root: Path | None) -> list[dict[str, str]]:
    result = client.query(
        """
        SELECT source, rule_id, severity, file, excerpt
        FROM skill_warden.findings
        WHERE run_id = {run_id:UUID}
        ORDER BY source, rule_id
        """,
        parameters={"run_id": str(run_id)},
    )
    rows: list[dict[str, str]] = []
    for source, rule_id, severity, file, excerpt in result.result_rows:
        file_text = str(file or "")
        if root is not None:
            file_text = relativize(file_text, root)
        rows.append(
            {
                "source": str(source),
                "ruleId": str(rule_id),
                "severity": str(severity),
                "file": file_text,
                "excerpt": str(excerpt or ""),
            }
        )
    return rows


def run_fixture(name: str, client) -> dict:
    root = SKILLS / name
    if not (root / "SKILL.md").is_file():
        raise SystemExit(f"missing fixture: {root}")
    flags = READER_FLAGS[name]
    captured: dict = {}

    def capturing_scan(paths, config):
        report = semgrep_scan(paths, config)
        captured["report"] = report
        return report

    record = SkillRecord(
        publisher="example",
        name=name,
        version="1.0.0",
        path=root,
        content_hash=content_hash(root),
    )
    store = RecordingStore(client)
    breaker = Breaker(
        max_usd=5.0,
        max_jobs=1,
        max_seconds=60,
        kill_path=root / "KILL",
    )
    reader = ScriptedReader(flags, READER_EVIDENCE.get(name, []))
    orchestrator = Orchestrator(store, breaker, RULES, reader, scan=capturing_scan)
    orchestrator.run(record)
    if store.last_run_id is None:
        raise SystemExit(f"{name}: orchestrator did not insert a run")
    decision, reason = store.verdict(store.last_run_id)
    expected = EXPECTED[name]
    if (decision, reason) != expected:
        raise SystemExit(f"{name}: got {decision}/{reason}, expected {expected[0]}/{expected[1]}")
    return {
        "name": name,
        "contentHash": record.content_hash,
        "files": skill_files(root),
        "semgrep": semgrep_hits(captured["report"], root),
        "reader": {"flags": flags, "scripted": True},
        "findings": finding_rows(client, store.last_run_id, root),
        "verdict": {"decision": decision, "reasonCode": reason},
    }


def plant_preview(path: Path, nonce: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    line = next((item for item in lines if nonce in item), lines[0] if lines else "")
    return line.replace(nonce, "…")


def run_jail(client) -> dict:
    argv = plan(Path("skill.tar"), JAIL_IMAGE, SINK_IP)
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp).resolve()
        plants = build_home(home, NONCE)
        body = plants[0].secret
        if search_nonce({"post": body}, NONCE) != ["post"]:
            raise SystemExit("search_nonce did not see the simulated post")
        exported = [
            {
                "path": plant.path.relative_to(home).as_posix(),
                "preview": plant_preview(plant.path, NONCE),
            }
            for plant in plants
        ]
    rows = build_rows(jail_events=[{"kind": "nonce"}])
    store = RecordingStore(client)
    breaker = Breaker(
        max_usd=5.0,
        max_jobs=1,
        max_seconds=60,
        kill_path=Path(tempfile.gettempdir()) / "skill-warden-demo-kill-absent",
    )
    breaker.enter(0.0)
    try:
        from uuid import uuid4

        run_id = uuid4()
        store.insert_run(run_id, "jail-simulated")
        store.insert_findings(run_id, rows)
        store.finish_run(run_id, "completed")
        decision, reason = store.verdict(run_id)
    finally:
        breaker.leave()
    if (decision, reason) != ("BLOCK", "canary"):
        raise SystemExit(f"jail: got {decision}/{reason}, expected BLOCK/canary")
    return {
        "argv": argv,
        "plants": exported,
        "simulatedRequest": {"url": "http://evil.example/collect", "response": '200 {"ok":true}'},
        "findings": finding_rows(client, run_id, None),
        "verdict": {"decision": decision, "reasonCode": reason},
    }


def main() -> None:
    client = connect()
    payload = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "verdictSql": load_sql(),
        "fixtures": [run_fixture(name, client) for name in EXPECTED],
        "jail": run_jail(client),
    }
    blob = json.dumps(payload, indent=2) + "\n"
    if NONCE in blob:
        raise SystemExit("refusing to write traces: nonce leaked into the JSON")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(blob, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    for fixture in payload["fixtures"]:
        verdict = fixture["verdict"]
        print(f"  {fixture['name']}: {verdict['decision']}/{verdict['reasonCode']}")
    jail = payload["jail"]["verdict"]
    print(f"  jail: {jail['decision']}/{jail['reasonCode']}")


if __name__ == "__main__":
    main()
