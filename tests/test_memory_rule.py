import tempfile
from pathlib import Path
from uuid import uuid4

from skill_warden.intake import load_skill, write_normalized
from skill_warden.models import RunOutcome
from skill_warden.policy import decide
from skill_warden.static.semgrep import rule_path, scan

ROOT = Path(__file__).resolve().parents[1]
LIVENESS = ROOT / "src" / "skill_warden" / "rules" / "liveness.yaml"
DOTSLASH = ROOT / "fixtures" / "skills" / "dotslash-memory"
ZERO_WIDTH = ROOT / "fixtures" / "skills" / "zero-width-memory"


def _scan(skill: Path):
    loaded = load_skill(skill)
    dest = Path(tempfile.mkdtemp())
    normalized = write_normalized(skill, loaded.record.files, dest)
    files = [dest / entry.relpath for entry in loaded.record.files if entry.kind == "text"]
    stage = scan(files, [rule_path(), LIVENESS], dest, timeout=30)
    outcome = RunOutcome(
        uuid4(),
        "completed",
        frozenset(("static",)),
        stage.findings,
        loaded.record.content_sha256,
        2,
    )
    return dest, normalized, stage, decide(outcome)


def test_dotslash_memory_is_block() -> None:
    _dest, normalized, stage, verdict = _scan(DOTSLASH)

    assert normalized == ()
    assert any(item.rule_id.endswith("skill-memory-file-persistence") for item in stage.findings)
    assert verdict.decision == "BLOCK"
    assert verdict.reason == "high_finding"


def test_zero_width_memory_is_block_from_the_normalized_copy() -> None:
    original = (ZERO_WIDTH / "SKILL.md").read_text(encoding="utf-8")
    dest, normalized, stage, verdict = _scan(ZERO_WIDTH)

    assert "\u200b" in original
    assert "\u200b" not in (dest / "SKILL.md").read_text(encoding="utf-8")
    assert any(item.rule_id == "obfuscation.unicode" for item in normalized)
    assert any(item.rule_id.endswith("skill-memory-file-persistence") for item in stage.findings)
    assert verdict.decision == "BLOCK"
    assert verdict.reason == "high_finding"
