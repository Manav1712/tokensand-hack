import importlib.util
import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / "scripts" / "ci.py"


def _load_ci():
    spec = importlib.util.spec_from_file_location("skill_warden_ci_mutate", CI_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(CI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stats(*, killed=0, survived=0, timeout=0, suspicious=0, no_tests=0):
    return {
        "killed": killed,
        "survived": survived,
        "timeout": timeout,
        "suspicious": suspicious,
        "no_tests": no_tests,
    }


def test_gate_fails_when_kill_rate_is_under_90():
    ci = _load_ci()
    # 8 killed of 10 = 80%.
    report = {"src/skill_warden/hashing.py": _stats(killed=8, survived=2)}

    problems = ci.mutation_problems(report, ["src/skill_warden/hashing.py"])

    assert problems
    assert any("hashing.py" in problem for problem in problems)


def test_gate_passes_hashing_at_90_percent():
    ci = _load_ci()
    report = {"src/skill_warden/hashing.py": _stats(killed=9, survived=1)}

    assert ci.mutation_problems(report, ["src/skill_warden/hashing.py"]) == []


def test_gate_requires_100_percent_on_policy():
    ci = _load_ci()
    report = {"src/skill_warden/policy.py": _stats(killed=99, survived=1)}

    problems = ci.mutation_problems(report, ["src/skill_warden/policy.py"])

    assert problems
    assert any("policy.py" in problem and "100" in problem for problem in problems)


def test_gate_fails_when_a_file_produces_no_mutants():
    ci = _load_ci()
    report = {"src/skill_warden/redact.py": _stats()}

    problems = ci.mutation_problems(report, ["src/skill_warden/redact.py"])

    assert any("redact.py" in problem for problem in problems)


def test_gate_counts_timeout_and_no_tests_as_not_killed():
    ci = _load_ci()
    # 9 killed + 1 timeout = 90% only if timeout counted as killed; it must not.
    report = {"src/skill_warden/hashing.py": _stats(killed=8, timeout=1, no_tests=1)}

    problems = ci.mutation_problems(report, ["src/skill_warden/hashing.py"])

    assert problems


def test_mutate_changed_with_no_core_paths_skips_mutmut():
    ci = _load_ci()
    calls: list[list[str]] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(list(argv))
        return 0

    code = ci.main(
        ["mutate", "--changed"],
        runner,
        changed_files=lambda: ["README.md", "tests/test_ci_script.py"],
    )

    assert code == 0
    assert calls == []


def test_mutate_changed_runs_mutmut_only_for_changed_core_file(monkeypatch, tmp_path):
    ci = _load_ci()
    stats_path = tmp_path / "mutmut-cicd-stats.json"
    monkeypatch.setattr(ci, "MUTMUT_STATS", stats_path)
    calls: list[list[str]] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(list(argv))
        if argv and argv[0] == "mutmut" and "export-cicd-stats" in argv:
            stats_path.write_text(
                '{"killed": 10, "survived": 0, "timeout": 0, '
                '"suspicious": 0, "no_tests": 0}',
                encoding="utf-8",
            )
        return 0

    code = ci.main(
        ["mutate", "--changed"],
        runner,
        changed_files=lambda: [
            "src/skill_warden/redact.py",
            "docs/progress.md",
        ],
    )

    assert code == 0
    run_calls = [call for call in calls if call[:2] == ["mutmut", "run"]]
    assert len(run_calls) == 1
    assert any("redact" in part for part in run_calls[0])


def test_mutate_runs_every_core_file(monkeypatch, tmp_path):
    ci = _load_ci()
    stats_path = tmp_path / "mutmut-cicd-stats.json"
    monkeypatch.setattr(ci, "MUTMUT_STATS", stats_path)
    calls: list[list[str]] = []

    def runner(argv: Sequence[str]) -> int:
        calls.append(list(argv))
        if argv and argv[0] == "mutmut" and "export-cicd-stats" in argv:
            stats_path.write_text(
                '{"killed": 10, "survived": 0, "timeout": 0, '
                '"suspicious": 0, "no_tests": 0}',
                encoding="utf-8",
            )
        return 0

    code = ci.main(["mutate"], runner)

    assert code == 0
    run_calls = [call for call in calls if call[:2] == ["mutmut", "run"]]
    assert len(run_calls) == 4
    patterns = [call[-1] for call in run_calls]
    assert "skill_warden.redact*" in patterns
    assert "skill_warden.hashing*" in patterns
    assert "skill_warden.policy*" in patterns
    assert "skill_warden.static.semgrep*" in patterns


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _feature_repo(tmp_path: Path, *, origin_main: bool, local_main: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.invalid")
    _git(repo, "config", "user.name", "dev")
    changed = repo / "changed.txt"
    changed.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "changed.txt")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-b", "feature")
    changed.write_text("base\nfeature\n", encoding="utf-8")
    _git(repo, "add", "changed.txt")
    _git(repo, "commit", "-m", "feature")
    if origin_main:
        _git(repo, "update-ref", "refs/remotes/origin/main", base)
    if not local_main:
        _git(repo, "branch", "-D", "main")
    return repo


def test_changed_files_use_origin_main_when_local_main_is_gone(monkeypatch, tmp_path):
    ci = _load_ci()
    repo = _feature_repo(tmp_path, origin_main=True, local_main=False)
    monkeypatch.setattr(ci, "ROOT", repo)

    assert ci._default_changed_files() == ["changed.txt"]


def test_changed_files_report_a_missing_base(monkeypatch, tmp_path):
    ci = _load_ci()
    repo = _feature_repo(tmp_path, origin_main=False, local_main=False)
    monkeypatch.setattr(ci, "ROOT", repo)

    try:
        ci._default_changed_files()
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected a missing base to fail")

    assert "origin/main" in message
    assert "main" in message
    assert "fatal:" in message


def test_changed_files_fall_back_to_local_main(monkeypatch, tmp_path):
    ci = _load_ci()
    repo = _feature_repo(tmp_path, origin_main=False, local_main=True)
    monkeypatch.setattr(ci, "ROOT", repo)

    assert ci._default_changed_files() == ["changed.txt"]
