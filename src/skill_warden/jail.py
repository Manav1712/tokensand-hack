import os
import re
import shlex
import subprocess
import tarfile
import uuid
from pathlib import Path
from uuid import UUID

from skill_warden import sink
from skill_warden.errors import JailError, SkillTreeError
from skill_warden.findings import build_rows
from skill_warden.honeytoken import build_home, search_nonce
from skill_warden.observe import events_from_diff, parse_strace_log
from skill_warden.registry import SkillRecord

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


def _skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if name == "HASH" or path.is_symlink() or not path.is_file():
                continue
            files.append(path)
    return sorted(files)


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


def detonate(
    record: SkillRecord,
    store,
    *,
    run_id: UUID,
    nonce: str,
    rules: Path,
    scratch: Path,
    timeout: int = 60,
    scan=None,
    on_ready=None,
) -> tuple[str, str]:
    if scan is None:
        from skill_warden.semgrep import scan as scan_fn

        scan = scan_fn

    pack_skill(record.path, scratch / "skill.tar")
    home_root = (scratch / "home").resolve()
    if home_root.exists():
        for child in home_root.iterdir():
            if child.is_dir():
                for sub in child.rglob("*"):
                    if sub.is_file():
                        sub.unlink()
                child.rmdir()
            elif child.is_file():
                child.unlink()
    plants = build_home(home_root, nonce)
    plant_paths = [str(p.path.relative_to(home_root)) for p in plants]
    secrets = list({p.secret for p in plants} | {nonce})

    semgrep_report = scan(_skill_files(record.path), rules)

    sink.build_image()
    build_jail_image()
    session = sink.start()
    container = f"skill-warden-jail-{uuid.uuid4().hex[:12]}"
    timed_out = False
    try:
        argv = [a for a in container_argv(scratch / "skill.tar", JAIL_IMAGE, sink.SINK_IP) if a != "--rm"]
        create_body = argv[2:]
        create = subprocess.run(
            ["docker", "create", "--name", container, *create_body],
            check=False, capture_output=True,
            text=True,
        )
        if create.returncode != 0:
            raise JailError(create.stderr.strip() or "docker create failed")
        start = subprocess.run(["docker", "start", container], check=False, capture_output=True, text=True)
        if start.returncode != 0:
            raise JailError(start.stderr.strip() or "docker start failed")
        if on_ready is not None:
            on_ready(container)

        _run(["docker", "exec", container, "mkdir", "-p", SKILL_ROOT])
        with (scratch / "skill.tar").open("rb") as skill_tar_file:
            streamed = subprocess.run(
                ["docker", "exec", "-i", container, "tar", "x", "-o", "-f", "-", "-C", SKILL_ROOT],
                check=False, input=skill_tar_file.read(),
                capture_output=True,
            )
        if streamed.returncode != 0:
            raise JailError(streamed.stderr.decode() or "tar stream skill failed")
        _stream_tree_into_container(container, home_root, AGENT_HOME)
        _run(["docker", "exec", container, "chmod", "-R", "a+rX", AGENT_HOME])
        _run(
            [
                "docker",
                "exec",
                container,
                "sh",
                "-c",
                f"chmod +x {SKILL_ROOT}/scripts/*.sh 2>/dev/null || true",
            ],
            check=False,
        )

        manifest = scratch / "jail-commands.txt"
        manifest.write_text(_manifest_lines(phase_commands(record.path)), encoding="utf-8")
        manifest_bytes = manifest.read_bytes()
        cp_manifest = subprocess.run(
            ["docker", "exec", "-i", container, "tee", "/tmp/jail-commands.txt"],
            check=False, input=manifest_bytes,
            capture_output=True,
        )
        if cp_manifest.returncode != 0:
            raise JailError(cp_manifest.stderr.decode() or "write manifest failed")

        try:
            traced = subprocess.run(
                ["docker", "exec", container, "/warden/run-phase.sh"],
                check=False, capture_output=True,
                text=True,
                timeout=timeout,
            )
            strace_text = traced.stdout + traced.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["docker", "kill", container], check=False, capture_output=True, text=True)
            strace_text = ""

        diff = subprocess.run(
            ["docker", "diff", container],
            check=False, capture_output=True,
            text=True,
        )
        diff_lines = diff.stdout.splitlines() if diff.returncode == 0 else []

        dns_text = sink.dns_log(session)
        http_text = sink.http_log(session)
        blobs = {"dns": dns_text, "http": http_text, "diff": "\n".join(diff_lines)}
        jail_events = events_from_observation(
            strace_text=strace_text,
            diff_lines=diff_lines,
            plant_paths=plant_paths,
            blobs=blobs,
            nonce=nonce,
            sink=sink.SINK_IP,
        )
        if timed_out:
            jail_events.append({"kind": "timeout"})

        rows = build_rows(
            semgrep=semgrep_report,
            jail_events=jail_events,
            sink=sink.SINK_IP,
            secrets=secrets,
        )
        store.insert_run(run_id, record.content_hash, backend="local")
        store.insert_findings(run_id, rows)
        finish_status = "timeout" if timed_out else "completed"
        store.finish_run(run_id, finish_status)
        return store.verdict(run_id)
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=False, capture_output=True, text=True)
        sink.stop(session)
