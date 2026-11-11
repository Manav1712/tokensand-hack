import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from skill_warden.models import Severity, Source
from skill_warden.static.semgrep import Completed, binary_name, resolve_binary, scan

ROOT = Path(__file__).resolve().parents[1]
LIVENESS = ROOT / "src" / "skill_warden" / "rules" / "liveness.yaml"
_SECRET = "super-secret-value"


def _python(tmp_path: Path) -> Path:
    path = tmp_path / "py" / "python"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    return path


def _binary(tmp_path: Path, name: str = "semgrep") -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _ids(result) -> list[str]:
    return [finding.rule_id for finding in result.findings]


def _hit(path: Path, *, check: str = "demo.rule", severity: str = "ERROR", line: object = 4) -> dict:
    start: dict[str, object] | None
    if line is None:
        start = None
    else:
        start = {"line": line}
    return {
        "check_id": check,
        "path": str(path),
        "start": start,
        "extra": {"message": "Instruction to write MEMORY.md", "severity": severity},
    }


def _payload(liveness: Path, skill: Path, *, results: list | None = None, scanned: list | None = None, errors: object = None) -> dict:
    body: dict[str, object] = {
        "results": [
            _hit(liveness, check="warden-liveness", severity="INFO", line=1),
        ]
        if results is None
        else results,
        "paths": {"scanned": [str(liveness), str(skill)] if scanned is None else scanned},
    }
    if errors is not None:
        body["errors"] = errors
    return body


def _capture(store: dict):
    def run(argv: Sequence[str], cwd: Path, env: dict, timeout: float) -> Completed:
        store["argv"] = list(argv)
        store["cwd"] = cwd
        store["env"] = dict(env)
        store["timeout"] = timeout
        liveness = next(path for path in cwd.iterdir() if path.name.startswith(".warden-liveness-"))
        skill = next(path for path in argv if path.endswith("note.md"))
        store["liveness"] = liveness
        payload = store.get("payload")
        if callable(payload):
            body = payload(liveness, Path(skill))
        else:
            body = payload
        text = body if isinstance(body, str) else json.dumps(body)
        return Completed(store.get("code", 0), text, bool(store.get("timed_out", False)))

    return run


def _scan(tmp_path: Path, store: dict, *, files: list[Path] | None = None, rules: list[Path] | None = None, **kwargs):
    work = tmp_path / "work"
    skill = work / "note.md"
    work.mkdir(exist_ok=True)
    for old in work.glob(".warden-liveness-*"):
        old.unlink()
    skill.write_text("hello\n", encoding="utf-8")
    chosen = files if files is not None else [skill]
    binary = _binary(tmp_path)
    return scan(
        chosen,
        [LIVENESS] if rules is None else rules,
        work,
        configured=kwargs.pop("configured", binary),
        run=_capture(store),
        **kwargs,
    )


def test_clean_run_drops_the_liveness_hit(tmp_path: Path) -> None:
    store: dict = {"payload": _payload}
    result = _scan(tmp_path, store)

    assert result.status == "ok"
    assert _ids(result) == ["semgrep.ok"]
    assert result.detail == ""
    assert result.findings[0].severity is Severity.INFO
    assert result.findings[0].source is Source.SEMGREP
    assert result.findings[0].excerpt == ""
    assert isinstance(result.elapsed_ms, int)
    argv = store["argv"]
    assert argv[1:8] == [
        "scan",
        "--json",
        "--metrics=off",
        "--disable-version-check",
        "--scan-unknown-extensions",
        "--timeout",
        "20",
    ]
    assert argv[0] == str(tmp_path / "semgrep")
    assert ["--config", str(LIVENESS)] == argv[8:10]
    assert str(store["liveness"]) in argv
    assert str(tmp_path / "work" / "note.md") in argv
    assert _SECRET not in store["env"].values()


def test_child_env_is_only_path_home_and_lang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_WARDEN_SECRET", _SECRET)
    monkeypatch.setenv("LANG", "C")
    store: dict = {"payload": _payload}

    _scan(tmp_path, store)

    assert set(store["env"]) <= {"PATH", "HOME", "LANG"}
    assert store["env"]["LANG"] == "C"
    assert _SECRET not in store["env"].values()


def test_missing_lang_is_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANG", raising=False)
    store: dict = {"payload": _payload}

    _scan(tmp_path, store)

    assert "LANG" not in store["env"]


def test_directory_is_not_a_target(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    store: dict = {"payload": _payload}

    _scan(tmp_path, store, files=[folder, tmp_path / "work" / "note.md"])

    assert str(folder) not in store["argv"]
    assert any(arg.endswith("note.md") for arg in store["argv"])


def test_two_rule_configs_are_both_passed(tmp_path: Path) -> None:
    extra = tmp_path / "extra.yaml"
    extra.write_text("rules: []\n", encoding="utf-8")
    store: dict = {"payload": _payload}

    _scan(tmp_path, store, rules=[LIVENESS, extra])

    assert store["argv"].count("--config") == 2
    assert str(extra) in store["argv"]


def test_configured_binary_beats_a_sibling(tmp_path: Path) -> None:
    exe = _python(tmp_path)
    sibling = exe.parent / binary_name()
    sibling.write_text("", encoding="utf-8")
    configured = _binary(tmp_path, "configured")
    store: dict = {"payload": _payload}

    _scan(tmp_path, store, configured=configured, executable=exe, which=lambda _name: str(tmp_path / "missing"))

    assert store["argv"][0] == str(configured)


def test_sibling_beats_path(tmp_path: Path, fake_binary) -> None:
    exe = _python(tmp_path)
    sibling = exe.parent / "semgrep"
    sibling.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sibling.chmod(0o755)
    path_bin = fake_binary("semgrep", "#!/bin/sh\nexit 9\n")
    store: dict = {"payload": _payload}
    work = tmp_path / "work"
    skill = work / "note.md"
    work.mkdir()
    skill.write_text("hello\n", encoding="utf-8")

    scan([skill], [LIVENESS], work, run=_capture(store), executable=exe)

    assert store["argv"][0] == str(sibling)
    assert store["argv"][0] != str(path_bin)


def test_path_is_used_when_there_is_no_sibling(tmp_path: Path) -> None:
    exe = _python(tmp_path)
    found = _binary(tmp_path, "from-path")
    resolved = resolve_binary(None, exe, lambda _name: str(found))

    assert resolved == found


def test_missing_configured_binary_does_not_fall_through(tmp_path: Path) -> None:
    missing = tmp_path / "missing-semgrep"
    result = scan([], [LIVENESS], tmp_path / "work", configured=missing, which=lambda _name: "/usr/bin/semgrep")

    assert result.status == "failed"
    assert _ids(result) == ["semgrep_unavailable"]
    assert result.detail == "semgrep_unavailable"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].source is Source.SEMGREP
    assert result.findings[0].excerpt == "reinstall skill-warden"


def test_missing_binary_with_fake_path(tmp_path: Path, fake_binary, monkeypatch: pytest.MonkeyPatch) -> None:
    decoy = fake_binary("not-semgrep", "#!/bin/sh\nexit 0\n")
    monkeypatch.setenv("PATH", str(decoy.parent))
    exe = decoy.parent / "python"
    exe.write_text("", encoding="utf-8")

    result = scan([], [LIVENESS], tmp_path / "work", executable=exe)

    assert result.status == "failed"
    assert _ids(result) == ["semgrep_unavailable"]


@pytest.mark.parametrize("name", ["posix", "nt"])
def test_binary_name(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setattr("skill_warden.static.semgrep.os.name", name)

    assert binary_name() == ("semgrep.exe" if name == "nt" else "semgrep")


def test_timeout_from_injected_run(tmp_path: Path) -> None:
    store: dict = {"payload": _payload, "timed_out": True}

    result = _scan(tmp_path, store)

    assert result.status == "timeout"
    assert _ids(result) == ["semgrep_timeout"]
    assert result.detail == "semgrep_timeout"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].source is Source.SEMGREP
    assert result.findings[0].excerpt == ""


def test_timeout_expired_is_semgrep_timeout(tmp_path: Path) -> None:
    def run(*_args: object) -> Completed:
        raise subprocess.TimeoutExpired(cmd="semgrep", timeout=1)

    result = scan([], [LIVENESS], tmp_path / "work", configured=_binary(tmp_path), run=run)

    assert result.status == "timeout"
    assert _ids(result) == ["semgrep_timeout"]
    assert result.detail == "semgrep_timeout"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].source is Source.SEMGREP
    assert result.findings[0].excerpt == ""


def test_runner_exception_is_semgrep_failed(tmp_path: Path) -> None:
    def run(*_args: object) -> Completed:
        raise RuntimeError("boom")

    result = scan([], [LIVENESS], tmp_path / "work", configured=_binary(tmp_path), run=run)

    assert result.status == "failed"
    assert result.detail == "run"
    assert result.findings[0].rule_id == "semgrep_failed"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].excerpt == "run"


def test_nonzero_exit_is_semgrep_failed(tmp_path: Path) -> None:
    store: dict = {"payload": '{"results": []}', "code": 2}

    result = _scan(tmp_path, store)

    assert result.status == "failed"
    assert result.findings[0].rule_id == "semgrep_failed"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].excerpt == "2"
    assert result.detail == "2"
    assert "semgrep.ok" not in _ids(result)


def test_garbage_stdout_is_semgrep_failed(tmp_path: Path) -> None:
    store: dict = {"payload": "not-json"}

    result = _scan(tmp_path, store)

    assert result.detail == "stdout"
    assert result.findings[0].rule_id == "semgrep_failed"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].excerpt == "stdout"


def test_stdout_without_results_is_semgrep_failed(tmp_path: Path) -> None:
    store: dict = {"payload": {"errors": []}}

    result = _scan(tmp_path, store)

    assert result.findings[0].rule_id == "semgrep_failed"
    assert result.detail == "stdout"


def test_non_object_stdout_is_semgrep_failed(tmp_path: Path) -> None:
    store: dict = {"payload": [1, 2]}

    result = _scan(tmp_path, store)

    assert result.detail == "stdout"


def test_engine_error_and_warning(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        body = _payload(liveness, skill)
        body["errors"] = [
            "not-a-dict",
            {"level": "warn", "message": "noisy"},
            {"level": "error", "message": "bad rule"},
            {"level": "info", "message": "ignored"},
        ]
        return body

    store: dict = {"payload": payload}
    result = _scan(tmp_path, store)

    assert "semgrep_error" in _ids(result)
    assert "semgrep_warning" in _ids(result)
    warning = next(item for item in result.findings if item.rule_id == "semgrep_warning")
    assert warning.severity is Severity.INFO
    assert warning.source is Source.SEMGREP
    error = next(item for item in result.findings if item.rule_id == "semgrep_error")
    assert error.severity is Severity.ERROR
    assert result.status == "failed"
    assert result.detail == "semgrep_error"


def test_errors_that_are_not_a_list_are_ignored(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        body = _payload(liveness, skill)
        body["errors"] = {"level": "error"}
        return body

    result = _scan(tmp_path, {"payload": payload})

    assert _ids(result) == ["semgrep.ok"]


def test_missing_target_is_target_not_scanned(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return _payload(liveness, skill, scanned=[str(liveness)])

    result = _scan(tmp_path, {"payload": payload})

    assert "target_not_scanned" in _ids(result)
    assert any(item.excerpt == "note.md" for item in result.findings)
    assert result.status == "failed"
    assert result.detail == "target_not_scanned"


def test_scanned_value_must_be_a_list(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return {
            "results": [_hit(liveness, check="warden-liveness", severity="INFO")],
            "paths": {"scanned": "note.md"},
        }

    result = _scan(tmp_path, {"payload": payload})

    assert "target_not_scanned" in _ids(result)


def test_paths_without_a_scanned_list_marks_every_target(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return {"results": [_hit(liveness, check="warden-liveness", severity="INFO")], "paths": []}

    result = _scan(tmp_path, {"payload": payload})

    assert _ids(result).count("target_not_scanned") == 2


def test_missing_liveness_hit_fails(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return _payload(liveness, skill, results=[])

    result = _scan(tmp_path, {"payload": payload})

    assert "semgrep_liveness_failed" in _ids(result)
    assert "semgrep.ok" not in _ids(result)
    assert result.detail == "semgrep_liveness_failed"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].excerpt == ""


def test_two_liveness_hits_fail(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        hit = _hit(liveness, check="warden-liveness", severity="INFO")
        return _payload(liveness, skill, results=[hit, dict(hit)])

    result = _scan(tmp_path, {"payload": payload})

    assert "semgrep_liveness_failed" in _ids(result)
    assert "warden-liveness" not in _ids(result)


def test_result_severities_and_line(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return _payload(
            liveness,
            skill,
            results=[
                _hit(liveness, check="pkg.warden-liveness", severity="INFO"),
                _hit(skill, check="rules.memory", severity="HIGH", line=8),
                _hit(skill, check="rules.medium", severity="MEDIUM", line=2),
                _hit(skill, check="rules.low", severity="LOW", line=3),
                _hit(skill, check="rules.info", severity="INFO", line=1),
                _hit(skill, check="rules.other", severity="BANANA", line=True),
                {"check_id": 3, "extra": []},
            ],
        )

    result = _scan(tmp_path, {"payload": payload})
    by_rule = {item.rule_id: item for item in result.findings}

    assert "pkg.warden-liveness" not in by_rule
    assert by_rule["rules.memory"].severity is Severity.HIGH
    assert by_rule["rules.memory"].line == 8
    assert by_rule["rules.memory"].file.endswith("note.md")
    assert "MEMORY.md" in by_rule["rules.memory"].excerpt
    assert by_rule["rules.medium"].severity is Severity.MEDIUM
    assert by_rule["rules.low"].severity is Severity.LOW
    assert by_rule["rules.info"].severity is Severity.INFO
    assert by_rule["rules.other"].severity is Severity.ERROR
    assert by_rule["rules.other"].line is None
    assert by_rule[""].rule_id == ""
    assert result.status == "failed"


def test_non_dict_result_is_semgrep_failed(tmp_path: Path) -> None:
    def payload(liveness: Path, skill: Path) -> dict:
        return _payload(
            liveness,
            skill,
            results=[
                "nope",
                _hit(liveness, check="warden-liveness", severity="INFO"),
                _hit(skill, check="rules.after", severity="LOW"),
            ],
        )

    result = _scan(tmp_path, {"payload": payload})

    assert "semgrep_liveness_failed" not in _ids(result)
    assert "rules.after" in _ids(result)
    assert any(item.excerpt == "result" and item.severity is Severity.ERROR for item in result.findings)


def _script(mode: str) -> str:
    return f"""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
mode = {mode!r}
files = [arg for arg in sys.argv[1:] if "warden-liveness" in arg or arg.endswith("note.md")]
liveness = next(arg for arg in files if "warden-liveness" in arg)
Path(liveness).with_name("probe.txt").write_text(
    os.getcwd() + "\\n" + ("leaked" if "SKILL_WARDEN_SECRET" in os.environ else "hidden"),
    encoding="utf-8",
)
if mode == "timeout":
    time.sleep(30)
if mode == "garbage":
    sys.stdout.write("not-json")
    raise SystemExit(0)
if mode == "exit":
    sys.stdout.write(json.dumps({{"results": []}}))
    raise SystemExit(2)
scanned = files
results = [{{
    "check_id": "warden-liveness",
    "path": liveness,
    "start": {{"line": 1}},
    "extra": {{"message": "canary", "severity": "INFO"}},
}}]
if mode == "omit-scanned":
    scanned = [liveness]
if mode == "no-liveness":
    results = []
if mode == "error":
    print(json.dumps({{"results": results, "paths": {{"scanned": scanned}}, "errors": [{{"level": "error"}}]}}))
    raise SystemExit(0)
if mode == "warn":
    print(json.dumps({{"results": results, "paths": {{"scanned": scanned}}, "errors": [{{"level": "warn"}}]}}))
    raise SystemExit(0)
print(json.dumps({{"results": results, "paths": {{"scanned": scanned}}}}))
"""


def _fake_scan(tmp_path: Path, fake_binary, mode: str, **kwargs):
    fake_binary("semgrep", _script(mode))
    exe = _python(tmp_path)
    work = tmp_path / "work"
    skill = work / "note.md"
    work.mkdir()
    skill.write_text("hello\n", encoding="utf-8")
    return scan([skill], [LIVENESS], work, executable=exe, timeout=kwargs.get("timeout", 10))


def test_fake_exit_code_is_semgrep_failed(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "exit")

    assert result.status == "failed"
    assert result.detail == "2"
    assert "semgrep.ok" not in _ids(result)


def test_fake_garbage_is_semgrep_failed(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "garbage")

    assert result.detail == "stdout"


def test_fake_timeout(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "timeout", timeout=0.2)

    assert result.status == "timeout"
    assert _ids(result) == ["semgrep_timeout"]
    assert result.detail == "semgrep_timeout"
    assert result.findings[0].severity is Severity.ERROR
    assert result.findings[0].source is Source.SEMGREP
    assert result.findings[0].excerpt == ""


def test_fake_omitted_target(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "omit-scanned")

    assert "target_not_scanned" in _ids(result)


def test_fake_missing_liveness_hit(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "no-liveness")

    assert "semgrep_liveness_failed" in _ids(result)


def test_fake_engine_error(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "error")

    assert "semgrep_error" in _ids(result)
    assert result.status == "failed"


def test_fake_warning_stays_ok(tmp_path: Path, fake_binary) -> None:
    result = _fake_scan(tmp_path, fake_binary, "warn")

    assert "semgrep_warning" in _ids(result)
    assert "semgrep.ok" in _ids(result)
    assert result.status == "ok"


def test_fake_clean_result(tmp_path: Path, fake_binary, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILL_WARDEN_SECRET", _SECRET)
    result = _fake_scan(tmp_path, fake_binary, "clean")
    probe = (tmp_path / "work" / "probe.txt").read_text(encoding="utf-8")

    assert _ids(result) == ["semgrep.ok"]
    assert result.status == "ok"
    assert probe.startswith(str(tmp_path / "work"))
    assert probe.endswith("hidden\n") or probe.splitlines()[-1] == "hidden"


def test_liveness_can_match_by_path_or_rule_id(tmp_path: Path) -> None:
    def by_path(liveness: Path, skill: Path) -> dict:
        return _payload(liveness, skill, results=[_hit(liveness, check="other.rule", severity="INFO")])

    def by_exact_id(liveness: Path, skill: Path) -> dict:
        hit = _hit(skill, check="warden-liveness", severity="INFO")
        return _payload(liveness, skill, results=[hit])

    def by_suffix(liveness: Path, skill: Path) -> dict:
        hit = _hit(skill, check="rules.warden-liveness", severity="INFO")
        return _payload(liveness, skill, results=[hit])

    for builder in (by_path, by_exact_id, by_suffix):
        result = _scan(tmp_path, {"payload": builder})
        assert "semgrep_liveness_failed" not in _ids(result)
        assert result.status == "ok"


def test_scan_uses_the_injected_lookup(tmp_path: Path) -> None:
    exe = _python(tmp_path)
    found = _binary(tmp_path, "from-which")
    store: dict = {"payload": _payload}
    work = tmp_path / "work"
    skill = work / "note.md"
    work.mkdir()
    skill.write_text("hello\n", encoding="utf-8")

    scan(
        [skill],
        [LIVENESS],
        work,
        run=_capture(store),
        executable=exe,
        which=lambda _name: str(found),
    )

    assert store["argv"][0] == str(found)


def test_scan_creates_missing_parents(tmp_path: Path) -> None:
    work = tmp_path / "missing" / "work"
    skill = tmp_path / "note.md"
    skill.write_text("hello\n", encoding="utf-8")
    store: dict = {"payload": _payload}

    result = scan([skill], [LIVENESS], work, configured=_binary(tmp_path), run=_capture(store))

    assert work.is_dir()
    assert result.status == "ok"


def test_real_semgrep_drops_the_liveness_hit(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    skill = work / "note.md"
    skill.write_text("hello\n", encoding="utf-8")

    result = scan([skill], [LIVENESS], work, timeout=30)

    assert result.status == "ok"
    assert _ids(result) == ["semgrep.ok"]
    assert isinstance(result.elapsed_ms, int) and result.elapsed_ms >= 1
    liveness = next(work.glob(".warden-liveness-*.txt"))
    nonce = liveness.name.removeprefix(".warden-liveness-").removesuffix(".txt")
    assert len(nonce) == 16
    assert liveness.read_text(encoding="utf-8") == f"WARDEN-LIVENESS-{nonce}\n"
