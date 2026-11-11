import hashlib
import os
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skill_warden.errors import SkillTreeError
from skill_warden.hashing import content_hash_v2


def _expected_v2(files: list[tuple[str, bytes, bool]]) -> str:
    digest = hashlib.sha256()
    for rel, data, executable in sorted(files, key=lambda item: item[0]):
        rel_b = os.fsencode(rel)
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
    script.chmod(0o744)
    owner_only = content_hash_v2(tmp_path)
    script.chmod(0o4644)
    setuid = content_hash_v2(tmp_path)

    assert plain != user
    assert owner_only == user == group == other
    assert setuid == plain


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


def test_v2_unlistable_directory_is_unreadable(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    hidden = tmp_path / "secret"
    hidden.mkdir()
    (hidden / "note.md").write_bytes(b"hidden")
    hidden.chmod(0)
    try:
        with pytest.raises(SkillTreeError, match="^unreadable$") as raised:
            content_hash_v2(tmp_path)
        assert str(hidden) not in str(raised.value)
    finally:
        hidden.chmod(0o755)


def test_v2_unreadable_file_is_unreadable(tmp_path: Path):
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"hello")
    skill.chmod(0)
    try:
        with pytest.raises(SkillTreeError, match="^unreadable$") as raised:
            content_hash_v2(tmp_path)
        assert str(skill) not in str(raised.value)
    finally:
        skill.chmod(0o644)


def test_v2_hashes_a_non_utf8_name(tmp_path: Path):
    (tmp_path / "SKILL.md").write_bytes(b"hello")
    raw_name = b"\xff.md"
    path = tmp_path / os.fsdecode(raw_name)
    path.write_bytes(b"x")

    assert content_hash_v2(tmp_path) == _expected_v2(
        [("SKILL.md", b"hello", False), (os.fsdecode(raw_name), b"x", False)]
    )


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
