import hashlib
import os
from pathlib import Path

from skill_warden.errors import SkillTreeError


def content_hash(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SkillTreeError(f"not a directory: {root}")

    files: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames:
            path = Path(dirpath) / name
            if path.is_symlink():
                raise SkillTreeError(f"symlink: {path}")
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                raise SkillTreeError(f"symlink: {path}")
            if name == "HASH" or not path.is_file():
                continue
            files.append((path.relative_to(root).as_posix(), path))

    digest = hashlib.sha256()
    for rel, path in sorted(files, key=lambda item: item[0]):
        data = path.read_bytes()
        rel_b = rel.encode("utf-8")
        digest.update(len(rel_b).to_bytes(8, "big"))
        digest.update(rel_b)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
