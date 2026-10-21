import hashlib

from skill_warden.findings import build_rows
from skill_warden.observe import events_from_diff, parse_strace, parse_strace_log

SINK = "10.0.0.2"


def _assert_row(row: dict, *, source: str, rule_id: str, severity: str, file: str, excerpt: str) -> None:
    assert row == {
        "source": source,
        "rule_id": rule_id,
        "severity": severity,
        "file": file,
        "excerpt": excerpt,
        "evidence_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
    }


def test_parse_strace_openat_success():
    got = parse_strace('openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3')

    assert got == {"syscall": "openat", "path": "/etc/ld.so.cache", "ret": "3"}


def test_parse_strace_open_normalized_to_openat():
    got = parse_strace('open("/etc/alpine-release", O_RDONLY|O_LARGEFILE) = 3')

    assert got == {"syscall": "openat", "path": "/etc/alpine-release", "ret": "3"}


def test_parse_strace_openat_enoent_kept():
    got = parse_strace(
        'openat(AT_FDCWD, "/home/agent/aws/credentials", O_RDONLY) = -1 ENOENT (No such file or directory)'
    )

    assert got is not None
    assert set(got) == {"syscall", "path", "ret"}
    assert got["syscall"] == "openat"
    assert got["path"] == "/home/agent/aws/credentials"
    assert isinstance(got["ret"], str)
    assert "ENOENT" in got["ret"]


def test_parse_strace_openat_eacces_kept():
    got = parse_strace('openat(AT_FDCWD, "/etc/shadow", O_RDONLY) = -1 EACCES (Permission denied)')

    assert got is not None
    assert set(got) == {"syscall", "path", "ret"}
    assert got["syscall"] == "openat"
    assert got["path"] == "/etc/shadow"
    assert isinstance(got["ret"], str)
    assert "EACCES" in got["ret"]


def test_parse_strace_relative_skill_md():
    got = parse_strace('openat(AT_FDCWD, "SKILL.md", O_RDONLY) = 3')

    assert got == {"syscall": "openat", "path": "SKILL.md", "ret": "3"}


def test_parse_strace_quoted_path_with_space():
    got = parse_strace('openat(AT_FDCWD, "/tmp/a b", O_RDONLY) = 3')

    assert got == {"syscall": "openat", "path": "/tmp/a b", "ret": "3"}


def test_parse_strace_pid_prefix_ignored():
    got = parse_strace('[pid 12] openat(AT_FDCWD, "/etc/passwd", O_RDONLY) = 3')

    assert got == {"syscall": "openat", "path": "/etc/passwd", "ret": "3"}


def test_parse_strace_execve_argv():
    got = parse_strace('execve("/bin/true", ["/bin/true", "--help"], 0x7ffe /* 1 var */) = 0')

    assert got == {
        "syscall": "execve",
        "path": "/bin/true",
        "argv": ["/bin/true", "--help"],
        "ret": "0",
    }


def test_parse_strace_execve_enoent_kept():
    got = parse_strace(
        'execve("/bin/missing", ["/bin/missing"], 0x1 /* 0 vars */) = -1 ENOENT (No such file or directory)'
    )

    assert got is not None
    assert set(got) == {"syscall", "path", "argv", "ret"}
    assert got["syscall"] == "execve"
    assert got["path"] == "/bin/missing"
    assert got["argv"] == ["/bin/missing"]
    assert isinstance(got["ret"], str)
    assert "ENOENT" in got["ret"]


def test_parse_strace_connect_ipv4():
    got = parse_strace(
        'connect(3, {sa_family=AF_INET, sin_port=htons(80), sin_addr=inet_addr("1.2.3.4")}, 16) = 0'
    )

    assert got == {"syscall": "connect", "dst": "1.2.3.4:80", "ret": "0"}


def test_parse_strace_connect_enetunreach_kept():
    got = parse_strace(
        'connect(3, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("1.1.1.1")}, 16)'
        " = -1 ENETUNREACH (Network is unreachable)"
    )

    assert got is not None
    assert set(got) == {"syscall", "dst", "ret"}
    assert got["syscall"] == "connect"
    assert got["dst"] == "1.1.1.1:53"
    assert isinstance(got["ret"], str)
    assert "ENETUNREACH" in got["ret"]


def test_parse_strace_connect_ipv6():
    got = parse_strace(
        'connect(3, {sa_family=AF_INET6, sin6_port=htons(443), sin6_addr=inet_pton(AF_INET6, "::1")}, 28) = 0'
    )

    assert got == {"syscall": "connect", "dst": "[::1]:443", "ret": "0"}


def test_parse_strace_connect_unix_enoent():
    got = parse_strace(
        'connect(3, {sa_family=AF_UNIX, sun_path="/var/run/docker.sock"}, 23)'
        " = -1 ENOENT (No such file or directory)"
    )

    assert got is not None
    assert set(got) == {"syscall", "dst", "ret"}
    assert got["syscall"] == "connect"
    assert got["dst"] == "/var/run/docker.sock"
    assert isinstance(got["ret"], str)
    assert "ENOENT" in got["ret"]


def test_parse_strace_close_returns_none():
    assert parse_strace("close(3) = 0") is None


def test_parse_strace_blank_returns_none():
    assert parse_strace("") is None


def test_parse_strace_exited_returns_none():
    assert parse_strace("+++ exited with 0 +++") is None


def test_parse_strace_truncated_returns_none():
    assert parse_strace('openat(AT_FDCWD, ') is None


def test_parse_strace_log_stitches_unfinished_openat():
    text = '[pid 12] openat(AT_FDCWD, "/home/agent/aws/credentials", O_RDONLY <unfinished ...>\n[pid 12] <... openat resumed>) = -1 ENOENT (No such file or directory)'
    records = parse_strace_log(text)

    assert len(records) == 1
    assert records[0]["path"] == "/home/agent/aws/credentials"
    assert isinstance(records[0]["ret"], str)
    assert "ENOENT" in records[0]["ret"]


def test_parse_strace_log_interleaved_pids_keep_paths():
    text = '[pid 12] openat(AT_FDCWD, "/tmp/one", O_RDONLY <unfinished ...>\n[pid 13] openat(AT_FDCWD, "/tmp/two", O_RDONLY <unfinished ...>\n[pid 13] <... openat resumed>) = 4\n[pid 12] <... openat resumed>) = 5'
    records = parse_strace_log(text)

    assert {record["path"]: record["ret"] for record in records} == {
        "/tmp/two": "4",
        "/tmp/one": "5",
    }


def test_parse_strace_log_orphan_resume_dropped():
    assert parse_strace_log("[pid 9] <... openat resumed>) = 3") == []


def test_parse_strace_log_complete_openat():
    records = parse_strace_log('openat(AT_FDCWD, "/etc/hostname", O_RDONLY) = 3')

    assert records == [{"syscall": "openat", "path": "/etc/hostname", "ret": "3"}]


def test_events_from_diff_added_and_changed():
    assert events_from_diff(["A /tmp/new", "C /home/agent/.bashrc"]) == [
        {"change": "added", "path": "/tmp/new"},
        {"change": "changed", "path": "/home/agent/.bashrc"},
    ]


def test_events_from_diff_deleted_omitted():
    assert events_from_diff(["D /tmp/old"]) == []


def test_events_from_diff_blank_and_malformed_omitted():
    assert events_from_diff(["", "not a diff line"]) == []


def test_events_from_diff_keeps_space_in_path():
    assert events_from_diff(["A /tmp/my file"]) == [{"change": "added", "path": "/tmp/my file"}]


def test_bashrc_diff_maps_to_persistence():
    changes = events_from_diff(["C /home/agent/.bashrc"])
    event = {"kind": "write", "path": changes[0]["path"]}
    rows = build_rows(jail_events=[event], sink=SINK)

    assert len(rows) == 1
    _assert_row(
        rows[0],
        source="jail",
        rule_id="persistence",
        severity="high",
        file="/home/agent/.bashrc",
        excerpt="",
    )


def test_dockerenv_read_maps_to_sandbox_probe():
    parsed = parse_strace('openat(AT_FDCWD, "/.dockerenv", O_RDONLY) = 3')
    event = {"kind": "read", "path": parsed["path"]}
    rows = build_rows(jail_events=[event], sink=SINK)

    assert len(rows) == 1
    _assert_row(
        rows[0],
        source="jail",
        rule_id="sandbox_probe",
        severity="high",
        file="/.dockerenv",
        excerpt="",
    )


def test_connect_egress_respects_sink():
    parsed = parse_strace(
        'connect(3, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.1.1.1")}, 16) = 0'
    )
    event = {"kind": "connect", "dst": parsed["dst"]}
    rows = build_rows(jail_events=[event], sink=SINK)

    assert len(rows) == 1
    _assert_row(
        rows[0],
        source="jail",
        rule_id="egress",
        severity="high",
        file="1.1.1.1:443",
        excerpt="",
    )
    assert build_rows(jail_events=[event], sink="1.1.1.1") == []
