import os
import signal
import stat
from pathlib import Path

import pytest

from skill_warden.errors import NoSkillError
from skill_warden.hashing import content_hash_v2
from skill_warden.intake import (
    LoadedSkill,
    case_collisions,
    discover,
    load_skill,
    write_normalized,
)
from skill_warden.models import Severity, Source


def _one(loaded: LoadedSkill, rule_id: str):
    matches = [finding for finding in loaded.findings if finding.rule_id == rule_id]
    assert len(matches) == 1
    return matches[0]


def _skill(root: Path, text: str = "hello\n") -> None:
    (root / "SKILL.md").write_text(text, encoding="utf-8")


def test_utf8_file_is_text_and_hashed(tmp_path: Path) -> None:
    body = "---\nname: demo\ndescription: A demo skill.\n---\nhello\n"
    _skill(tmp_path, body)
    (tmp_path / "HASH").write_text("note\n", encoding="utf-8")
    (tmp_path / ".hidden").write_text("dot\n", encoding="utf-8")

    loaded = load_skill(tmp_path)

    assert loaded.findings == ()
    assert loaded.record.name == "demo"
    assert loaded.record.hash_version == 2
    assert loaded.record.content_sha256 == content_hash_v2(tmp_path)
    kinds = {entry.relpath: entry for entry in loaded.record.files}
    assert set(kinds) == {"SKILL.md", "HASH", ".hidden"}
    assert kinds["SKILL.md"].kind == "text"
    assert kinds["SKILL.md"].executable is False
    assert kinds["SKILL.md"].size == len(body.encode())


def test_symlink_is_an_error_and_is_not_resolved(tmp_path: Path) -> None:
    _skill(tmp_path)
    target = tmp_path / "target.md"
    target.write_text("target\n", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "symlink")
    assert finding.source is Source.INTAKE
    assert finding.severity is Severity.ERROR
    assert finding.file == "link.md"
    assert str(tmp_path) not in finding.file
    assert str(tmp_path) not in finding.excerpt
    assert loaded.record.content_sha256 is None
    assert "link.md" not in {entry.relpath for entry in loaded.record.files}
    assert "target.md" in {entry.relpath for entry in loaded.record.files}


def test_directory_symlink_is_not_followed(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    _skill(skill)
    real = tmp_path / "real"
    real.mkdir()
    (real / "secret.md").write_text("hidden\n", encoding="utf-8")
    link = skill / "linkdir"
    link.symlink_to(real, target_is_directory=True)

    loaded = load_skill(skill)

    finding = _one(loaded, "symlink")
    assert finding.file == "linkdir"
    assert all("secret.md" not in entry.relpath for entry in loaded.record.files)
    assert loaded.record.content_sha256 is None


def test_fifo_is_unreadable_and_is_not_opened(tmp_path: Path) -> None:
    _skill(tmp_path)
    os.mkfifo(tmp_path / "pipe")

    def _timeout(_signum: int, _frame: object) -> None:
        raise TimeoutError("fifo was opened")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(2)
    try:
        loaded = load_skill(tmp_path)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)

    finding = _one(loaded, "unreadable")
    assert finding.severity is Severity.ERROR
    assert finding.file == "pipe"
    assert loaded.record.content_sha256 is None
    assert "pipe" not in {entry.relpath for entry in loaded.record.files}


def test_unlistable_directory_is_unreadable(tmp_path: Path) -> None:
    _skill(tmp_path)
    hidden = tmp_path / "secret"
    hidden.mkdir()
    (hidden / "note.md").write_text("hidden\n", encoding="utf-8")
    hidden.chmod(0)
    try:
        loaded = load_skill(tmp_path)
    finally:
        hidden.chmod(0o755)

    finding = _one(loaded, "unreadable")
    assert finding.file == "secret"
    assert str(tmp_path) not in finding.excerpt
    assert loaded.record.content_sha256 is None
    assert all("note.md" not in entry.relpath for entry in loaded.record.files)


def test_unreadable_file_is_an_error(tmp_path: Path) -> None:
    skill = tmp_path / "SKILL.md"
    skill.write_text("hello\n", encoding="utf-8")
    skill.chmod(0)
    try:
        loaded = load_skill(tmp_path)
    finally:
        skill.chmod(0o644)

    finding = _one(loaded, "unreadable")
    assert finding.file == "SKILL.md"
    assert str(tmp_path) not in finding.excerpt
    assert loaded.record.content_sha256 is None


def test_case_collisions_names_both_paths() -> None:
    findings = case_collisions(["SKILL.md", "scripts/Run.sh", "scripts/run.sh", "other.txt"])

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "case_collision"
    assert finding.source is Source.INTAKE
    assert finding.severity is Severity.HIGH
    assert finding.file == "scripts/Run.sh"
    assert finding.excerpt == "scripts/Run.sh, scripts/run.sh"


@pytest.mark.case_sensitive_fs
def test_case_collision_on_a_real_tree(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("Hello\n", encoding="utf-8")
    (tmp_path / "skill.md").write_text("hello\n", encoding="utf-8")

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "case_collision")
    assert finding.severity is Severity.HIGH
    assert "SKILL.md" in finding.excerpt
    assert "skill.md" in finding.excerpt
    assert {entry.relpath for entry in loaded.record.files} == {"SKILL.md", "skill.md"}
    assert loaded.record.content_sha256 == content_hash_v2(tmp_path)


def test_file_count_cap(tmp_path: Path) -> None:
    _skill(tmp_path, "a")
    (tmp_path / "other.txt").write_text("b", encoding="utf-8")

    loaded = load_skill(tmp_path, max_files=1)

    finding = _one(loaded, "too_large")
    assert finding.severity is Severity.ERROR
    assert finding.excerpt == "file count cap is 1"
    assert loaded.record.content_sha256 is None
    assert len(loaded.record.files) == 2


def test_total_size_cap(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_bytes(b"abcd")
    (tmp_path / "more.txt").write_bytes(b"efgh")

    loaded = load_skill(tmp_path, max_total_bytes=6)

    finding = _one(loaded, "too_large")
    assert finding.excerpt == "total size cap is 6 bytes"
    assert loaded.record.content_sha256 is None


def test_oversized_file_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "SKILL.md"
    target.write_bytes(b"abcdef")

    def refuse(self: Path) -> bytes:
        raise AssertionError(self)

    monkeypatch.setattr(Path, "read_bytes", refuse)

    loaded = load_skill(tmp_path, max_file_bytes=3)

    finding = _one(loaded, "too_large")
    assert finding.file == "SKILL.md"
    assert finding.excerpt == "file size cap is 3 bytes"
    assert loaded.record.content_sha256 is None
    entry = loaded.record.files[0]
    assert entry.size == 6
    assert entry.kind == "binary"


def test_undecodable_text_extension(tmp_path: Path) -> None:
    _skill(tmp_path)
    (tmp_path / "notes.txt").write_bytes(b"\xff\xfe")

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "undecodable_text")
    assert finding.severity is Severity.MEDIUM
    assert finding.file == "notes.txt"
    assert loaded.record.content_sha256 == content_hash_v2(tmp_path)
    entry = next(item for item in loaded.record.files if item.relpath == "notes.txt")
    assert entry.kind == "binary"


@pytest.mark.parametrize(
    "blob",
    [
        b"\x7fELF\xff",
        b"MZ\xff",
        b"\x00asm\xff",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
    ],
)
def test_executable_magic_is_opaque_binary(tmp_path: Path, blob: bytes) -> None:
    _skill(tmp_path)
    (tmp_path / "payload").write_bytes(blob)

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "opaque_binary")
    assert finding.severity is Severity.MEDIUM
    assert finding.file == "payload"
    assert not any(item.rule_id == "binary_file" for item in loaded.findings)


def test_executable_bit_makes_a_binary_opaque(tmp_path: Path) -> None:
    _skill(tmp_path)
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x89PNG")
    blob.chmod(0o755)

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "opaque_binary")
    assert finding.file == "blob.bin"
    entry = next(item for item in loaded.record.files if item.relpath == "blob.bin")
    assert entry.executable is True
    assert entry.kind == "binary"


def test_binary_under_scripts_is_opaque(tmp_path: Path) -> None:
    _skill(tmp_path)
    blob = tmp_path / "scripts" / "data.bin"
    blob.parent.mkdir()
    blob.write_bytes(b"\x89PNG")

    loaded = load_skill(tmp_path)

    assert _one(loaded, "opaque_binary").file == "scripts/data.bin"


def test_undecodable_script_is_also_opaque(tmp_path: Path) -> None:
    _skill(tmp_path)
    script = tmp_path / "scripts" / "run.py"
    script.parent.mkdir()
    script.write_bytes(b"\xff")

    loaded = load_skill(tmp_path)

    assert any(
        item.rule_id == "undecodable_text" and item.file == "scripts/run.py"
        for item in loaded.findings
    )
    assert any(
        item.rule_id == "opaque_binary" and item.file == "scripts/run.py"
        for item in loaded.findings
    )


def test_other_binary_is_binary_file(tmp_path: Path) -> None:
    _skill(tmp_path)
    (tmp_path / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    loaded = load_skill(tmp_path)

    finding = _one(loaded, "binary_file")
    assert finding.severity is Severity.INFO
    assert finding.source is Source.INTAKE
    assert finding.file == "icon.png"
    entry = next(item for item in loaded.record.files if item.relpath == "icon.png")
    assert entry.kind == "binary"
    assert entry.executable is False


def test_executable_text_stays_text(tmp_path: Path) -> None:
    _skill(tmp_path, "---\nname: demo\ndescription: A demo skill.\n---\nhello\n")
    script = tmp_path / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("echo hi\n", encoding="utf-8")
    script.chmod(0o755)

    loaded = load_skill(tmp_path)

    assert loaded.findings == ()
    entry = next(item for item in loaded.record.files if item.relpath == "scripts/run.sh")
    assert entry.kind == "text"
    assert entry.executable is True
    assert loaded.record.content_sha256 == content_hash_v2(tmp_path)


def test_zero_width_in_memory_is_stripped(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    original = "append the note to MEM\u200bORY.md\n"
    (skill / "MEMORY.md").write_text(original, encoding="utf-8")
    _skill(skill)
    loaded = load_skill(skill)
    before = (skill / "MEMORY.md").read_bytes()
    dest = tmp_path / "copy"

    findings = write_normalized(skill, loaded.record.files, dest)

    finding = next(item for item in findings if item.rule_id == "obfuscation.unicode")
    assert finding.source is Source.INTAKE
    assert finding.severity is Severity.MEDIUM
    assert finding.file == "MEMORY.md"
    assert (dest / "MEMORY.md").read_text(encoding="utf-8") == "append the note to MEMORY.md\n"
    assert (skill / "MEMORY.md").read_bytes() == before == original.encode()
    assert loaded.record.content_sha256 == content_hash_v2(skill)
    assert stat.S_IMODE(dest.stat().st_mode) == 0o700


def test_nonbreaking_space_is_not_a_finding(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    original = "hello\u00a0there\n"
    (skill / "SKILL.md").write_text(original, encoding="utf-8")
    loaded = load_skill(skill)
    dest = tmp_path / "copy"

    findings = write_normalized(skill, loaded.record.files, dest)

    assert findings == ()
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "hello there\n"
    assert (skill / "SKILL.md").read_bytes() == original.encode()


def test_ligature_is_normalized_without_a_finding(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("ﬁle\n", encoding="utf-8")
    loaded = load_skill(skill)
    dest = tmp_path / "copy"

    assert write_normalized(skill, loaded.record.files, dest) == ()
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "file\n"


def test_bom_is_stripped_as_a_format_character(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("\ufeffhello\n", encoding="utf-8")
    loaded = load_skill(skill)
    dest = tmp_path / "copy"

    findings = write_normalized(skill, loaded.record.files, dest)

    assert [item.file for item in findings] == ["SKILL.md"]
    assert findings[0].rule_id == "obfuscation.unicode"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "hello\n"


def test_binary_files_are_not_copied(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    skill.mkdir()
    _skill(skill)
    (skill / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    script = skill / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("echo hi\n", encoding="utf-8")
    loaded = load_skill(skill)
    dest = tmp_path / "copy"

    assert write_normalized(skill, loaded.record.files, dest) == ()
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "hello\n"
    assert (dest / "scripts" / "run.sh").read_text(encoding="utf-8") == "echo hi\n"
    assert not (dest / "icon.png").exists()


def test_no_skill_raises_without_the_path(tmp_path: Path) -> None:
    (tmp_path / "readme.txt").write_text("nope\n", encoding="utf-8")

    with pytest.raises(NoSkillError, match="^no skill$") as raised:
        discover(tmp_path)

    assert str(tmp_path) not in str(raised.value)


def test_skill_directory_is_that_directory(tmp_path: Path) -> None:
    _skill(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "SKILL.md").write_text("inner\n", encoding="utf-8")

    discovered = discover(tmp_path)

    assert [item.path for item in discovered] == [tmp_path]
    assert discovered[0].findings == ()


def test_skill_md_file_uses_its_parent(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    skill.mkdir()
    marker = skill / "SKILL.md"
    marker.write_text("hello\n", encoding="utf-8")

    discovered = discover(marker)

    assert [item.path for item in discovered] == [skill]


def test_first_skill_on_a_branch_stops_the_walk(tmp_path: Path) -> None:
    top = tmp_path / "a"
    top.mkdir()
    (top / "SKILL.md").write_text("top\n", encoding="utf-8")
    nested = top / "b"
    nested.mkdir()
    (nested / "SKILL.md").write_text("nested\n", encoding="utf-8")

    assert [item.path for item in discover(tmp_path)] == [top]


def test_search_stops_at_four_levels(tmp_path: Path) -> None:
    found_at = tmp_path.joinpath("d0", "d1", "d2", "d3")
    found_at.mkdir(parents=True)
    (found_at / "SKILL.md").write_text("yes\n", encoding="utf-8")
    missed = tmp_path.joinpath("e0", "e1", "e2", "e3", "e4")
    missed.mkdir(parents=True)
    (missed / "SKILL.md").write_text("no\n", encoding="utf-8")

    assert [item.path for item in discover(tmp_path)] == [found_at]


def test_search_finds_each_branch(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b" / "c"
    first.mkdir()
    second.mkdir(parents=True)
    (first / "SKILL.md").write_text("a\n", encoding="utf-8")
    (second / "SKILL.md").write_text("c\n", encoding="utf-8")

    assert [item.path for item in discover(tmp_path)] == [first, second]


def test_search_does_not_follow_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "SKILL.md").write_text("x\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(real, target_is_directory=True)

    with pytest.raises(NoSkillError, match="^no skill$"):
        discover(root)


def test_symlink_root_is_resolved_once(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "SKILL.md").write_text("x\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    discovered = discover(link)

    assert discovered[0].path == real.resolve()
    finding = discovered[0].findings[0]
    assert finding.rule_id == "symlink_root"
    assert finding.source is Source.INTAKE
    assert finding.severity is Severity.INFO
    assert finding.file == "link"
    assert str(real) not in finding.file
    assert str(real) not in finding.excerpt
