from pathlib import Path

import pytest

from skill_warden.errors import SkillTreeError
from skill_warden.jail import pack_skill, plan


def test_pack_skill_refuses_symlink_escaping_src(tmp_path):
    src = tmp_path / "skill"
    src.mkdir()
    (src / "SKILL.md").write_text("---\n")
    (src / "escape").symlink_to("/etc/passwd")
    dest = tmp_path / "skill.tar"

    with pytest.raises(SkillTreeError):
        pack_skill(src, dest)


def test_plan_argv_contains_hardening_flags():
    argv = plan(Path("/unused/skill.tar"), "warden/jail:latest", "172.28.0.2")

    assert argv[0:3] == ["docker", "run", "--rm"]
    assert "--network" in argv and argv[argv.index("--network") + 1] == "jailnet"
    assert "--dns" in argv and argv[argv.index("--dns") + 1] == "172.28.0.2"
    assert "--cap-drop=ALL" in argv
    assert "--cap-add=SETUID" in argv
    assert "--cap-add=SETGID" in argv
    assert "--security-opt" in argv
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert "--read-only" in argv
    assert "--pids-limit" in argv and argv[argv.index("--pids-limit") + 1] == "128"
    mem_idx = argv.index("--memory")
    swap_idx = argv.index("--memory-swap")
    assert argv[mem_idx + 1] == "256m"
    assert argv[swap_idx + 1] == argv[mem_idx + 1]
    assert "--tmpfs" in argv
    tmpfs_vals = [argv[i + 1] for i, a in enumerate(argv) if a == "--tmpfs"]
    assert "/tmp:rw,nosuid,nodev,size=64m" in tmpfs_vals
    assert "/home/agent:rw,nosuid,nodev,size=64m" in tmpfs_vals
    assert argv[-1] == "warden/jail:latest"


def test_plan_argv_does_not_leak_host_paths():
    home = str(Path.home())
    argv = plan(Path(home) / "skill.tar", "img@sha256:abc", "10.0.0.1")
    joined = " ".join(argv)

    assert home not in joined
    assert "docker.sock" not in joined
    assert "-v" not in argv
