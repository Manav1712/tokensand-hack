import hashlib
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skill_warden.errors import SkillTreeError
from skill_warden.hashing import content_hash, content_hash_v2, skill_files


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


def _expected_v2(files: list[tuple[str, bytes, bool]]) -> str:
    digest = hashlib.sha256()
    for rel, data, executable in sorted(files, key=lambda item: item[0]):
        rel_b = rel.encode("utf-8")
        digest.update(len(rel_b).to_bytes(8, "big"))
        digest.update(rel_b)
        digest.update(b"x" if executable else b"-")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _chmod(path: Path, executable: bool) -> None:
    path.chmod(0o755 if executable else 0o644)


def test_content_hash_v2_matches_length_prefixed_entries(tmp_path: Path):
    files = [
        ("SKILL.md", b"hello", False),
        ("scripts/run.sh", b"echo\n", True),
        (".env", b"X", False),
        ("HASH", b"note", False),
    ]
    for rel, data, executable in files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        _chmod(path, executable)

    assert content_hash_v2(tmp_path) == _expected_v2(files)


def test_hash_file_changes_v2_digest(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    _chmod(skill, False)
    before = content_hash_v2(tmp_path)
    marker = tmp_path / "HASH"
    marker.write_bytes(b"deadbeef")
    _chmod(marker, False)

    assert content_hash_v2(tmp_path) != before


def test_dotfile_changes_v2_digest(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    _chmod(skill, False)
    before = content_hash_v2(tmp_path)
    hidden = tmp_path / ".hidden"
    hidden.write_bytes(b"secret")
    _chmod(hidden, False)

    assert content_hash_v2(tmp_path) != before


def test_one_byte_change_changes_v2_digest(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    _chmod(skill, False)
    before = content_hash_v2(tmp_path)
    skill.write_bytes(b"hellp")

    assert content_hash_v2(tmp_path) != before


def test_path_change_changes_v2_digest(tmp_path: Path):
    skill = tmp_path / "a.md"
    skill.write_bytes(b"hello")
    _chmod(skill, False)
    before = content_hash_v2(tmp_path)
    skill.rename(tmp_path / "b.md")

    assert content_hash_v2(tmp_path) != before


def test_execute_bit_changes_v2_digest(tmp_path: Path):
    script = tmp_path / "run.sh"
    script.write_bytes(b"echo hi\n")
    script.chmod(0o644)
    plain = content_hash_v2(tmp_path)
    script.chmod(0o755)
    user = content_hash_v2(tmp_path)
    script.chmod(0o674)
    group = content_hash_v2(tmp_path)
    script.chmod(0o645)
    other = content_hash_v2(tmp_path)

    assert plain != user
    assert user == group == other


def test_v2_hash_ignores_write_order(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root, names in ((first, ("b.txt", "a.txt")), (second, ("a.txt", "b.txt"))):
        root.mkdir()
        for name in names:
            path = root / name
            path.write_bytes(name.encode())
            _chmod(path, False)

    assert content_hash_v2(first) == content_hash_v2(second)


def test_v2_empty_directory(tmp_path: Path):
    assert content_hash_v2(tmp_path) == hashlib.sha256().hexdigest()


def test_v2_skips_a_socket(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    _chmod(skill, False)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(tmp_path / "sock"))
    try:
        assert content_hash_v2(tmp_path) == _expected_v2([("SKILL.md", b"hello", False)])
    finally:
        sock.close()


def test_v2_symlink_raises(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    link = tmp_path / "link.md"
    link.symlink_to(skill)

    with pytest.raises(SkillTreeError, match=f"symlink: {link}"):
        content_hash_v2(tmp_path)


def test_v2_directory_symlink_raises(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    nested = tmp_path / "nested"
    nested.mkdir()
    linkdir = tmp_path / "linkdir"
    linkdir.symlink_to(nested, target_is_directory=True)

    with pytest.raises(SkillTreeError, match=f"symlink: {linkdir}"):
        content_hash_v2(tmp_path)


def test_v2_file_path_raises(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")

    with pytest.raises(SkillTreeError, match=f"not a directory: {skill}"):
        content_hash_v2(skill)


def test_v2_root_symlink_raises(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(SkillTreeError, match=f"not a directory: {link}"):
        content_hash_v2(link)


def _names():
    piece = st.text(alphabet="abcdefghij", min_size=1, max_size=6)
    return st.one_of(st.just("HASH"), st.just(".hidden"), piece)


def _relpath():
    return st.lists(_names(), min_size=1, max_size=2).map("/".join)


def _no_path_prefix(files: list[tuple[str, bytes, bool]]) -> bool:
    paths = [rel for rel, _, _ in files]
    return all(
        left == right or (not right.startswith(left + "/") and not left.startswith(right + "/"))
        for left in paths
        for right in paths
    )


_trees = st.lists(
    st.tuples(_relpath(), st.binary(max_size=8), st.booleans()),
    min_size=1,
    max_size=4,
    unique_by=lambda item: item[0],
).filter(_no_path_prefix)


def _hash_tree(files: list[tuple[str, bytes, bool]]) -> str:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        for rel, data, executable in files:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            _chmod(path, executable)
        return content_hash_v2(root)


@given(_trees)
def test_v2_hash_changes_with_bytes_path_or_execute_bit(files):
    original = _hash_tree(files)

    assert original == _expected_v2(files)
    assert _hash_tree(list(reversed(files))) == original

    rel, data, executable = files[0]
    assert _hash_tree([(rel, data + b"\x00", executable), *files[1:]]) != original
    assert _hash_tree([(rel + "-x", data, executable), *files[1:]]) != original
    assert _hash_tree([(rel, data, not executable), *files[1:]]) != original
