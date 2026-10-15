import hashlib
from pathlib import Path

import pytest

from skill_warden.hashing import content_hash
from skill_warden.errors import SkillTreeError


def _expected_digest(files: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for rel, data in sorted(files, key=lambda item: item[0]):
        rel_b = rel.encode("utf-8")
        digest.update(len(rel_b).to_bytes(8, "big"))
        digest.update(rel_b)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _write_skill(root: Path) -> list[tuple[str, bytes]]:
    skill = root / "SKILL.md"
    skill.write_bytes(b"name: format-date\n")
    script = root / "scripts" / "format_date.py"
    script.parent.mkdir()
    script.write_bytes(b"def format_date():\n    return '2026-10-09'\n")
    return [
        ("SKILL.md", skill.read_bytes()),
        ("scripts/format_date.py", script.read_bytes()),
    ]


def test_content_hash_matches_path_and_bytes(tmp_path: Path):
    files = _write_skill(tmp_path)

    assert content_hash(tmp_path) == _expected_digest(files)


def test_one_byte_change_changes_digest(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    before = content_hash(tmp_path)
    skill.write_bytes(b"hellp")

    assert content_hash(tmp_path) != before


def test_hash_file_does_not_change_digest(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    before = content_hash(tmp_path)
    (tmp_path / "HASH").write_bytes(b"deadbeef")

    assert content_hash(tmp_path) == before


def test_symlink_raises(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    (tmp_path / "link.md").symlink_to(tmp_path / "SKILL.md")

    with pytest.raises(SkillTreeError):
        content_hash(tmp_path)


def test_file_path_raises(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")

    with pytest.raises(SkillTreeError):
        content_hash(skill)
