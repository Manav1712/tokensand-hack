import hashlib
from pathlib import PurePosixPath

from skill_warden.redact import excerpt, redact

_HIGH = {"ERROR", "CRITICAL", "HIGH"}
_MEDIUM = {"WARNING", "MEDIUM"}
_DIRECT = {"INFO": "info", "LOW": "low"}
_READER_HIGH = {
    "indirect_injection",
    "credential_exfil",
    "memory_persistence",
    "shell_callback",
}
_READER_MEDIUM = {"false_safety_claim", "obfuscation"}
_READER_KEYS = {"flags", "evidence"}
_PROBE_MARKERS = ("/.dockerenv", "/proc/1/cgroup", "TracerPid")
_PERSISTENCE_MARKERS = (".bashrc", ".git/hooks", "cron", "/skills/")


def build_rows(
    *,
    semgrep: dict | None = None,
    reader: object = None,
    canary_log: str = "",
    jail_events: list[dict] | None = None,
    sink: str = "",
    secrets: list[str] | None = None,
    rules_requested: list[str] | None = None,
    rules_loaded: int | None = None,
    prompt_canary: str = "",
) -> list[dict[str, str]]:
    secret_list = [] if secrets is None else secrets
    rows: list[dict[str, str]] = []
    if semgrep is not None:
        rows.extend(_semgrep_rows(semgrep, secret_list))
    if _ruleset_empty(rules_requested, rules_loaded):
        rows.append(_row("policy", "ruleset_empty", "error", "", ""))
    if reader is not None:
        rows.extend(_reader_rows(reader, secret_list, prompt_canary))
    if canary_log:
        rows.append(_row("canary", "canary.tripped", "critical", "", "[canary tripped]"))
    if jail_events:
        rows.extend(_jail_rows(jail_events, sink))
    return rows


def _jail_rows(events: list[dict], sink: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        if kind in ("honeytoken_open", "nonce"):
            rows.append(_row("canary", "honeytoken", "critical", "", "[canary tripped]"))
            continue
        if kind == "connect":
            dst = str(event.get("dst") or "")
            if dst and not _connects_to_sink(dst, sink):
                rows.append(_row("jail", "egress", "high", dst, ""))
            continue
        if kind == "read":
            path = str(event.get("path") or "")
            if _path_contains(path, _PROBE_MARKERS):
                rows.append(_row("jail", "sandbox_probe", "high", path, ""))
            if "TracerPid" in path:
                rows.append(_row("jail", "observer_attack", "high", path, ""))
            continue
        if kind == "write":
            path = str(event.get("path") or "")
            if _path_contains(path, _PERSISTENCE_MARKERS):
                rows.append(_row("jail", "persistence", "high", path, ""))
            continue
        if kind == "sleep":
            seconds = event.get("seconds")
            if isinstance(seconds, (int, float)) and seconds > 30:
                rows.append(_row("jail", "delay", "high", "", ""))
            continue
        if kind == "timeout":
            rows.append(_row("jail", "delay", "high", "", ""))
            continue
        if kind == "tracer_died":
            rows.append(_row("jail", "observer_attack", "high", "", ""))
    return rows


def _connects_to_sink(dst: str, sink: str) -> bool:
    if not sink:
        return False
    host = dst.rsplit(":", 1)[0] if ":" in dst and dst.rsplit(":", 1)[-1].isdigit() else dst
    return host == sink


def _path_contains(path: str, markers: tuple[str, ...]) -> bool:
    return any(marker in path for marker in markers)


def _semgrep_rows(semgrep: dict, secrets: list[str]) -> list[dict[str, str]]:
    if not isinstance(semgrep, dict):
        return []
    rows: list[dict[str, str]] = []
    results = semgrep.get("results")
    if isinstance(results, list):
        for result in results:
            rows.append(_result_row(result, secrets))
        if not results:
            rows.append(_row("semgrep", "semgrep.ok", "info", "", ""))
    skill_md = _first_skill_md(semgrep)
    if skill_md:
        rows.append(_row("policy", "skill_md_skipped", "error", skill_md, ""))
    return rows


def _result_row(result: dict, secrets: list[str]) -> dict[str, str]:
    extra = result.get("extra") or {}
    message = str(extra.get("message") or "")
    return _row(
        "semgrep",
        str(result.get("check_id") or ""),
        _severity(str(extra.get("severity") or "")),
        str(result.get("path") or ""),
        excerpt(redact(message, secrets)),
    )


def _severity(raw: str) -> str:
    key = raw.strip().upper()
    if key in _HIGH:
        return "high"
    if key in _MEDIUM:
        return "medium"
    if key in _DIRECT:
        return _DIRECT[key]
    return "error"


def _first_skill_md(semgrep: dict) -> str:
    for path in _paths(semgrep):
        if PurePosixPath(path).name == "SKILL.md":
            return path
    return ""


def _paths(semgrep: dict) -> list[str]:
    errors = semgrep.get("errors") or []
    skipped = (semgrep.get("paths") or {}).get("skipped") or []
    paths: list[str] = []
    for item in list(skipped) + list(errors):
        if isinstance(item, str):
            paths.append(item)
        elif isinstance(item, dict) and "path" in item:
            paths.append(str(item["path"]))
    return paths


def _ruleset_empty(rules_requested: list[str] | None, rules_loaded: int | None) -> bool:
    if rules_requested is None or rules_loaded is None:
        return False
    return "p/agent-skills" in rules_requested and rules_loaded == 0


def _reader_rows(reader: object, secrets: list[str], prompt_canary: str) -> list[dict[str, str]]:
    if not _valid_reader(reader) or _contains(reader, prompt_canary):
        return [_row("reader", "reader_invalid", "error", "", "")]
    flags = reader["flags"]
    if any(flag not in _READER_HIGH and flag not in _READER_MEDIUM for flag in flags):
        return [_row("reader", "reader_invalid", "error", "", "")]
    text = excerpt(redact("\n".join(reader["evidence"]), secrets))
    rows: list[dict[str, str]] = []
    for flag in flags:
        severity = "high" if flag in _READER_HIGH else "medium"
        rows.append(_row("reader", flag, severity, "", text))
    return rows


def _valid_reader(reader: object) -> bool:
    if not isinstance(reader, dict) or set(reader) != _READER_KEYS:
        return False
    flags = reader["flags"]
    evidence = reader["evidence"]
    if not isinstance(flags, list) or not isinstance(evidence, list):
        return False
    return all(isinstance(flag, str) for flag in flags) and all(isinstance(item, str) for item in evidence)


def _contains(value: object, needle: str) -> bool:
    if not needle:
        return False
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(_contains(key, needle) or _contains(item, needle) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return needle in str(value)


def _row(source: str, rule_id: str, severity: str, file: str, excerpt_text: str) -> dict[str, str]:
    return {
        "source": source,
        "rule_id": rule_id,
        "severity": severity,
        "file": file,
        "excerpt": excerpt_text,
        "evidence_hash": hashlib.sha256(excerpt_text.encode()).hexdigest(),
    }
