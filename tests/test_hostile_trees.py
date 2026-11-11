import json
import os
import signal
import unicodedata
from pathlib import Path

import pytest

from skill_warden.hashing import content_hash_v2
from skill_warden.intake import MAX_FILE_BYTES, load_skill
from skill_warden.models import Severity

_FRONT = "---\nname: demo\ndescription: A demo skill.\n---\n"


def _skill(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(_FRONT, encoding="utf-8")


def _rule(loaded, rule_id: str):
    matches = [finding for finding in loaded.findings if finding.rule_id == rule_id]
    assert matches
    return matches[0]


def test_thirty_levels_are_inventoried(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    current = skill
    for index in range(30):
        current = current / f"d{index}"
    current.mkdir(parents=True)
    (skill / "SKILL.md").write_text(_FRONT, encoding="utf-8")
    (current / "deep.txt").write_text("x\n", encoding="utf-8")

    loaded = load_skill(skill)

    relpath = "/".join(f"d{index}" for index in range(30)) + "/deep.txt"
    assert any(entry.relpath == relpath for entry in loaded.record.files)
    assert not any(finding.severity is Severity.ERROR for finding in loaded.findings)


def test_long_name_is_inventoried(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    name = "n" * 255
    (skill / name).write_text("x\n", encoding="utf-8")

    loaded = load_skill(skill)

    assert any(entry.relpath == name for entry in loaded.record.files)
    assert not any(finding.severity is Severity.ERROR for finding in loaded.findings)


def test_invalid_utf8_name_is_a_finding(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    raw = b"\xff.md"
    (skill / os.fsdecode(raw)).write_bytes(b"x")

    loaded = load_skill(skill)

    finding = _rule(loaded, "bad_filename")
    assert finding.severity is Severity.ERROR
    assert loaded.record.content_sha256 is None
    rendered = json.dumps([item.to_row() for item in loaded.findings])
    rendered.encode("utf-8")
    assert "udcff" not in rendered.lower()
    for item in loaded.findings:
        item.file.encode("utf-8")
        item.excerpt.encode("utf-8")


def test_symlink_loop_is_a_symlink_finding(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    loop = skill / "loop"
    loop.symlink_to("loop")

    loaded = load_skill(skill)

    finding = _rule(loaded, "symlink")
    assert finding.file == "loop"
    assert finding.severity is Severity.ERROR
    assert str(skill) not in finding.excerpt
    assert loaded.record.content_sha256 is None


def test_fifo_is_unreadable_and_is_not_opened(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    os.mkfifo(skill / "pipe")

    def _timeout(_signum: int, _frame: object) -> None:
        raise TimeoutError("fifo was opened")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(2)
    try:
        loaded = load_skill(skill)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)

    finding = _rule(loaded, "unreadable")
    assert finding.file == "pipe"
    assert finding.severity is Severity.ERROR
    assert loaded.record.content_sha256 is None


def test_sparse_file_over_the_cap_is_not_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    big = skill / "big.bin"
    with big.open("wb") as handle:
        handle.seek(MAX_FILE_BYTES + 1)
        handle.write(b"x")
    original = Path.read_bytes

    def guarded(self: Path) -> bytes:
        if self == big:
            raise AssertionError("sparse file was read")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", guarded)

    loaded = load_skill(skill)

    finding = _rule(loaded, "too_large")
    assert "file size cap" in finding.excerpt
    assert finding.severity is Severity.ERROR
    assert loaded.record.content_sha256 is None
    assert any(entry.relpath == "big.bin" for entry in loaded.record.files)


def test_nfkc_names_collide_and_both_are_kept(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    _skill(skill)
    ligature = "\uff41.md"
    plain = "a.md"
    assert unicodedata.normalize("NFKC", ligature) == plain
    assert ligature.casefold() != plain.casefold()
    (skill / ligature).write_text("one\n", encoding="utf-8")
    (skill / plain).write_text("two\n", encoding="utf-8")

    loaded = load_skill(skill)

    finding = _rule(loaded, "nfkc_collision")
    assert finding.severity is Severity.HIGH
    assert ligature in finding.excerpt
    assert plain in finding.excerpt
    names = {entry.relpath for entry in loaded.record.files}
    assert {ligature, plain} <= names
    assert loaded.record.content_sha256 == content_hash_v2(skill)
    assert not any(item.rule_id == "case_collision" for item in loaded.findings)
