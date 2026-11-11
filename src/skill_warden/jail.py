"""Jail plan and skill packing. Detonation itself returns in M6."""

import os
import tarfile
from pathlib import Path

from skill_warden.errors import SkillTreeError

_PIDS_LIMIT = "128"
_MEMORY = "256m"
_TMPFS_TMP = "/tmp:rw,nosuid,nodev,size=64m"
_TMPFS_HOME = "/home/agent:rw,nosuid,nodev,size=64m"
AGENT_HOME = "/home/agent"


def plan(skill_tar: Path, image: str, sink_ip: str) -> list[str]:
    del skill_tar  # used by later steps; not embedded in argv
    proxy = f"http://{sink_ip}:80"
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "jailnet",
        "--dns",
        sink_ip,
        "--cap-drop=ALL",
        "--cap-add=SETUID",
        "--cap-add=SETGID",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--pids-limit",
        _PIDS_LIMIT,
        "--memory",
        _MEMORY,
        "--memory-swap",
        _MEMORY,
        "--tmpfs",
        _TMPFS_TMP,
        "--tmpfs",
        _TMPFS_HOME,
        "-e",
        f"HOME={AGENT_HOME}",
        "-e",
        "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "-e",
        f"HTTP_PROXY={proxy}",
        "-e",
        f"HTTPS_PROXY={proxy}",
        image,
    ]


def _resolve_under_root(link: Path, root: Path) -> Path:
    target = os.path.normpath(os.path.join(os.path.dirname(link), os.readlink(link)))
    resolved = (Path(target) if os.path.isabs(target) else root / target).resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SkillTreeError(f"symlink escapes skill root: {link}") from exc
    return resolved


def pack_skill(src: Path, dest_tar: Path) -> None:
    if src.is_symlink() or not src.is_dir():
        raise SkillTreeError(f"not a directory: {src}")

    root = src.resolve()
    members: list[tuple[str, Path, bool]] = []

    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(src).as_posix()
            if path.is_symlink():
                _resolve_under_root(path, root)
                members.append((rel, path, True))
            elif path.is_file():
                members.append((rel, path, False))

    dest_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_tar, "w") as tar:
        for rel, path, is_link in sorted(members, key=lambda item: item[0]):
            if is_link:
                info = tarfile.TarInfo(name=rel)
                link_target = os.readlink(path)
                info.type = tarfile.SYMTYPE
                info.linkname = link_target
                info.size = 0
                tar.addfile(info)
            else:
                tar.add(path, arcname=rel, recursive=False)
