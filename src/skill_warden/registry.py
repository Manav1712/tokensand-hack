from dataclasses import dataclass
from pathlib import Path

from skill_warden.hashing import content_hash


@dataclass(frozen=True)
class SkillRecord:
    publisher: str
    name: str
    version: str
    path: Path
    content_hash: str


def scan(root: Path) -> list[SkillRecord]:
    records: list[SkillRecord] = []
    for publisher_dir in root.iterdir():
        if not publisher_dir.is_dir():
            continue
        for name_dir in publisher_dir.iterdir():
            if not name_dir.is_dir():
                continue
            for version_dir in name_dir.iterdir():
                if not version_dir.is_dir():
                    continue
                if not (version_dir / "SKILL.md").is_file():
                    continue
                records.append(
                    SkillRecord(
                        publisher=publisher_dir.name,
                        name=name_dir.name,
                        version=version_dir.name,
                        path=version_dir,
                        content_hash=content_hash(version_dir),
                    )
                )
    return sorted(records, key=lambda record: (record.publisher, record.name, record.version))
