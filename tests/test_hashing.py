import hashlib
from pathlib import Path

import pytest

from skill_warden.errors import SkillTreeError
from skill_warden.hashing import content_hash, skill_files


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
    link = tmp_path / "link.md"
    link.symlink_to(tmp_path / "SKILL.md")

    with pytest.raises(SkillTreeError, match=f"symlink: {link}"):
        content_hash(tmp_path)


def test_directory_symlink_raises(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    nested = tmp_path / "nested"
    nested.mkdir()
    linkdir = tmp_path / "linkdir"
    linkdir.symlink_to(nested, target_is_directory=True)

    with pytest.raises(SkillTreeError, match=f"symlink: {linkdir}"):
        content_hash(tmp_path)


def test_skill_files_skips_hash_and_symlinks(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text("hello\n", encoding="utf-8")
    (tmp_path / "HASH").write_text("nope\n", encoding="utf-8")
    (tmp_path / "link.md").symlink_to(tmp_path / "SKILL.md")

    assert skill_files(tmp_path) == [tmp_path / "SKILL.md"]


def test_skill_files_does_not_follow_directory_symlinks(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.md").write_text("secret\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "SKILL.md").write_text("hello\n", encoding="utf-8")
    (root / "linkdir").symlink_to(outside, target_is_directory=True)

    assert skill_files(root) == [root / "SKILL.md"]


def test_content_hash_orders_by_relative_path_string(tmp_path: Path):
    # "a-b" sorts before "a/b" as strings; Path("a-b") sorts after Path("a/b").
    (tmp_path / "a-b").write_bytes(b"one")
    nested = tmp_path / "a"
    nested.mkdir()
    (nested / "b").write_bytes(b"two")

    assert content_hash(tmp_path) == _expected_digest(
        [("a-b", b"one"), ("a/b", b"two")]
    )


def test_file_path_raises(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")

    with pytest.raises(SkillTreeError, match=f"not a directory: {skill}"):
        content_hash(skill)
