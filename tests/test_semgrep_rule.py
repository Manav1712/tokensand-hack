import shutil
from pathlib import Path

from skill_warden.semgrep import rule_path, scan

ROOT = Path(__file__).resolve().parents[1]
RULE = rule_path()
MEMORY = ROOT / "fixtures" / "skills" / "memory-poison" / "SKILL.md"
CLEAN = ROOT / "fixtures" / "skills" / "clean-date" / "SKILL.md"


def _matches_persistence(report: dict) -> bool:
    return any(
        str(result.get("check_id", "")).endswith("skill-memory-file-persistence")
        for result in report["results"]
    )


def test_memory_poison_matches_persistence_rule():
    report = scan([MEMORY], RULE)

    assert _matches_persistence(report)


def test_clean_date_has_no_results():
    report = scan([CLEAN], RULE)

    assert report["results"] == []


def test_skill_semgrep_yml_does_not_hide_match(tmp_path: Path):
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

    report = scan([skill / "SKILL.md"], RULE)

    assert _matches_persistence(report)
