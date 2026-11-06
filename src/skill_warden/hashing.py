import hashlib
import os
import stat
from pathlib import Path

from skill_warden.errors import SkillTreeError

_EXECUTE = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def content_hash(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SkillTreeError(f"not a directory: {root}")

    files: list[tuple[str, Path]] = []
    # Default followlinks=False. Dir symlinks are rejected below before descent.
    for dirpath, dirnames, filenames in os.walk(root):
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


def _unreadable(_error: OSError) -> None:
    raise SkillTreeError("unreadable") from None


def content_hash_v2(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise SkillTreeError(f"not a directory: {root}")

    files: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root, onerror=_unreadable):
        for name in dirnames:
            path = Path(dirpath) / name
            if path.is_symlink():
                raise SkillTreeError(f"symlink: {path}")
        for name in filenames:
            path = Path(dirpath) / name
            if path.is_symlink():
                raise SkillTreeError(f"symlink: {path}")
            if path.is_file():
                files[path.relative_to(root).as_posix()] = path

    digest = hashlib.sha256()
    for rel in sorted(files):
        path = files[rel]
        try:
            data = path.read_bytes()
            mode = path.stat().st_mode
        except OSError:
            raise SkillTreeError("unreadable") from None
        rel_b = os.fsencode(rel)
        digest.update(len(rel_b).to_bytes(8, "big"))
        digest.update(rel_b)
        digest.update(_mode_byte(mode))
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _mode_byte(mode: int) -> bytes:
    if mode & _EXECUTE:
        return b"x"
    return b"-"


def skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    # Default followlinks=False; directory symlinks are not walked.
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath) / name
            if name == "HASH" or path.is_symlink() or not path.is_file():
                continue
            files.append(path)
    return sorted(files)
