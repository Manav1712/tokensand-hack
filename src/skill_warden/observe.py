import re

_PID = re.compile(r"^\[pid\s+\d+\]\s*")
_CALL = re.compile(
    r"^(?P<syscall>openat|execve|connect)\((?P<args>.*)\)\s*=\s*(?P<ret>.+?)\s*$"
)
_QUOTED = re.compile(r'"((?:\\.|[^"\\])*)"')
_RET = re.compile(r"(-?\d+)(?:\s+([A-Z][A-Z0-9]*))?")
_EXECVE = re.compile(r'\s*"((?:\\.|[^"\\])*)"\s*,\s*\[(.*?)\]', re.DOTALL)
_INET4 = re.compile(
    r'sin_port=htons\(\s*(\d+)\s*\).*?sin_addr=inet_addr\("([^"]*)"\)'
)
_INET6 = re.compile(
    r'sin6_port=htons\(\s*(\d+)\s*\).*?inet_pton\(\s*AF_INET6\s*,\s*"([^"]*)"\s*\)'
)
_UNIX = re.compile(r'sun_path="((?:\\.|[^"\\])*)"')
_UNFINISHED = re.compile(
    r"^(?:\[pid\s+(?P<pid>\d+)\]\s+)?(?P<body>.+?)\s*<unfinished \.\.\.>\s*$"
)
_RESUMED = re.compile(
    r"^(?:\[pid\s+(?P<pid>\d+)\]\s+)?<\.\.\.\s+\w+\s+resumed>(?P<rest>.*)$"
)
_DIFF = {"A": "added", "C": "changed"}


def parse_strace(line: str) -> dict | None:
    try:
        return _parse_strace(line)
    except Exception:  # noqa: BLE001
        return None


def parse_strace_log(text: str) -> list[dict]:
    pending: dict[str, str] = {}
    records: list[dict] = []
    for line in text.splitlines():
        resumed = _RESUMED.match(line.strip())
        if resumed is not None:
            body = pending.pop(resumed.group("pid") or "", None)
            if body is None:
                continue
            record = parse_strace(body + resumed.group("rest"))
            if record is not None:
                records.append(record)
            continue
        unfinished = _UNFINISHED.match(line.strip())
        if unfinished is not None:
            pending[unfinished.group("pid") or ""] = unfinished.group("body")
            continue
        record = parse_strace(line)
        if record is not None:
            records.append(record)
    return records


def events_from_diff(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        if len(line) < 2 or line[1] != " ":
            continue
        change = _DIFF.get(line[0])
        if change is None:
            continue
        events.append({"change": change, "path": line[2:]})
    return events


def _parse_strace(line: str) -> dict | None:
    stripped = _PID.sub("", line.strip(), count=1)
    match = _CALL.match(stripped)
    if match is None:
        return None
    ret = _parse_ret(match.group("ret"))
    if ret is None:
        return None
    syscall = match.group("syscall")
    args = match.group("args")
    if syscall == "openat":
        path = _first_quoted(args)
        if path is None:
            return None
        return {"syscall": "openat", "path": path, "ret": ret}
    if syscall == "execve":
        parsed = _parse_execve(args)
        if parsed is None:
            return None
        path, argv = parsed
        return {"syscall": "execve", "path": path, "argv": argv, "ret": ret}
    dst = _connect_dst(args)
    if dst is None:
        return None
    return {"syscall": "connect", "dst": dst, "ret": ret}


def _parse_ret(raw: str) -> str | None:
    match = _RET.match(raw.strip())
    if match is None:
        return None
    errno = match.group(2)
    if errno:
        return errno
    return match.group(1)


def _first_quoted(text: str) -> str | None:
    match = _QUOTED.search(text)
    if match is None:
        return None
    return match.group(1)


def _parse_execve(args: str) -> tuple[str, list[str]] | None:
    match = _EXECVE.match(args)
    if match is None:
        return None
    argv = _QUOTED.findall(match.group(2))
    return match.group(1), argv


def _connect_dst(args: str) -> str | None:
    if "AF_UNIX" in args or "sun_path=" in args:
        match = _UNIX.search(args)
        if match is None:
            return None
        return match.group(1)
    inet6 = _INET6.search(args)
    if inet6 is not None:
        return f"[{inet6.group(2)}]:{inet6.group(1)}"
    inet4 = _INET4.search(args)
    if inet4 is not None:
        return f"{inet4.group(2)}:{inet4.group(1)}"
    return None
