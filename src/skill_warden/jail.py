import os
import re
import shlex
import subprocess
import tarfile
from pathlib import Path

from skill_warden.errors import JailError, SkillTreeError
from skill_warden.honeytoken import search_nonce
from skill_warden.observe import events_from_diff, parse_strace_log

_PIDS_LIMIT = "128"
_MEMORY = "256m"
_TMPFS_TMP = "/tmp:rw,nosuid,nodev,size=64m"
_TMPFS_HOME = "/home/agent:rw,nosuid,nodev,size=64m"
AGENT_HOME = "/home/agent"
SKILL_ROOT = "/tmp/skill"
JAIL_IMAGE = "skill-warden-jail:step17"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_JAIL_BUILD_CONTEXT = _REPO_ROOT / "docker" / "jail"
_BASH_FENCE = re.compile(r"```(?:bash|sh)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


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


def container_argv(skill_tar: Path, image: str, sink_ip: str) -> list[str]:
    return plan(skill_tar, image, sink_ip) + ["sleep", "infinity"]


def phase_commands(skill_root: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    scripts_dir = skill_root / "scripts"
    if scripts_dir.is_dir():
        for script in sorted(scripts_dir.glob("*.sh")):
            in_jail = f"{SKILL_ROOT}/scripts/{script.name}"
            commands.append(["/bin/sh", in_jail])
            commands.append(["/bin/sh", in_jail, "--help"])
    skill_md = skill_root / "SKILL.md"
    if skill_md.is_file():
        text = skill_md.read_text(encoding="utf-8")
        for match in _BASH_FENCE.finditer(text):
            block = match.group(1).strip()
            if not block:
                continue
            commands.append(["/bin/sh", "-c", block])
    return commands


def events_from_observation(
    *,
    strace_text: str,
    diff_lines: list[str],
    plant_paths: list[str],
    blobs: dict[str, str],
    nonce: str,
    sink: str,
) -> list[dict]:
    events: list[dict] = []
    plant_abs = {f"{AGENT_HOME}/{rel}".rstrip("/") for rel in plant_paths}
    for record in parse_strace_log(strace_text):
        syscall = record.get("syscall")
        if syscall == "openat":
            path = str(record.get("path") or "")
            ret = str(record.get("ret") or "")
            if path in plant_abs and ret != "ENOENT":
                events.append({"kind": "honeytoken_open"})
            elif ret != "ENOENT":
                events.append({"kind": "read", "path": path})
        elif syscall == "connect":
            dst = str(record.get("dst") or "")
            if not dst or "/" in dst:
                continue
            if ":" not in dst:
                continue
            host = dst.rsplit(":", 1)[0]
            if host.startswith("["):
                host = host[1:-1]
            if host and host != sink:
                events.append({"kind": "connect", "dst": dst})
    for item in events_from_diff(diff_lines):
        events.append({"kind": "write", "path": item["path"]})
    if search_nonce(blobs, nonce):
        events.append({"kind": "nonce"})
    return events


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
        for rel, path, is_link in sorted(members, key=lambda m: m[0]):
            if is_link:
                info = tarfile.TarInfo(name=rel)
                link_target = os.readlink(path)
                info.type = tarfile.SYMTYPE
                info.linkname = link_target
                info.size = 0
                tar.addfile(info)
            else:
                tar.add(path, arcname=rel, recursive=False)


def _run(args: list[str], *, timeout: int | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        raise JailError(result.stderr.strip() or " ".join(args))
    return result


def build_jail_image() -> None:
    build = subprocess.run(
        ["docker", "build", "-t", JAIL_IMAGE, str(_JAIL_BUILD_CONTEXT)],
        check=False, capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        raise JailError(build.stderr.strip() or "docker build jail failed")


def _manifest_lines(commands: list[list[str]]) -> str:
    if not commands:
        return "true\n"
    return "\n".join(shlex.join(cmd) for cmd in commands) + "\n"


def _stream_tree_into_container(container: str, host_root: Path, dest: str) -> None:
    import io

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for dirpath, _dirnames, filenames in os.walk(host_root):
            for name in filenames:
                host_path = Path(dirpath) / name
                rel = host_path.relative_to(host_root).as_posix()
                tar.add(host_path, arcname=rel, recursive=False)
    streamed = subprocess.run(
        ["docker", "exec", "-i", container, "tar", "x", "-o", "-f", "-", "-C", dest],
        check=False, input=buf.getvalue(),
        capture_output=True,
    )
    if streamed.returncode != 0:
        raise JailError(streamed.stderr.decode() or "tar stream home failed")
