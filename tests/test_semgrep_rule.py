import shutil
from pathlib import Path

from skill_warden.static.semgrep import rule_path, scan

ROOT = Path(__file__).resolve().parents[1]
LIVENESS = ROOT / "src" / "skill_warden" / "rules" / "liveness.yaml"
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison" / "SKILL.md"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date" / "SKILL.md"


def _matched(result) -> bool:
    return any(
        finding.rule_id.endswith("skill-memory-file-persistence") for finding in result.findings
    )


def test_memory_poison_matches_persistence_rule(tmp_path: Path) -> None:
    result = scan([MEMORY], [rule_path(), LIVENESS], tmp_path, timeout=30)

    assert _matched(result)


def test_clean_date_has_no_persistence_rule(tmp_path: Path) -> None:
    result = scan([CLEAN], [rule_path(), LIVENESS], tmp_path, timeout=30)

    assert not _matched(result)


def test_skill_semgrep_yml_does_not_hide_match(tmp_path: Path) -> None:
    skill = tmp_path / "memory-poison"
    shutil.copytree(MEMORY.parent, skill)
    (skill / ".semgrep.yml").write_text(
        "rules:\n"
        "  - id: suppress\n"
        "    languages: [generic]\n"
        "    severity: INFO\n"
        "    pattern-regex: a^\n"
        "    paths:\n"
        "      exclude:\n"
        "        - SKILL.md\n",
        encoding="utf-8",
    )
    work = tmp_path / "work"

    result = scan([skill / "SKILL.md"], [rule_path(), LIVENESS], work, timeout=30)

    assert _matched(result)
