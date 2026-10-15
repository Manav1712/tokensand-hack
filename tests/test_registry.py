from dataclasses import fields
from pathlib import Path

from skill_warden.hashing import content_hash
from skill_warden.registry import SkillRecord, scan


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_scan_returns_sorted_records(tmp_path: Path):
    _write(tmp_path / "zeta" / "format-date" / "1.0.0" / "SKILL.md", b"name: format-date\n")
    _write(tmp_path / "alpha" / "format-date" / "2.0.0" / "SKILL.md", b"name: format-date\n")
    _write(tmp_path / "alpha" / "format-date" / "9.9.9" / "README.md", b"not a skill\n")

    records = scan(tmp_path)

    assert [(r.publisher, r.name, r.version) for r in records] == [
        ("alpha", "format-date", "2.0.0"),
        ("zeta", "format-date", "1.0.0"),
    ]
    for record in records:
        assert record.content_hash == content_hash(record.path)


def test_hash_file_is_not_a_record_field(tmp_path: Path):
    version = tmp_path / "alpha" / "format-date" / "1.0.0"
    _write(version / "SKILL.md", b"name: format-date\n")
    _write(version / "HASH", b"deadbeef")

    records = scan(tmp_path)

    assert len(records) == 1
    assert isinstance(records[0], SkillRecord)
    assert [field.name for field in fields(records[0])] == [
        "publisher",
        "name",
        "version",
        "path",
        "content_hash",
    ]
