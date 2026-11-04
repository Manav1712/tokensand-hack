import os
import shutil
import stat
import subprocess
from pathlib import Path


def test_fake_binary_puts_an_executable_first_on_path(fake_binary):
    script = "#!/bin/sh\necho FAKE-CANARY\nexit 2\n"

    path = fake_binary("warden-fake-bin", script)

    assert path.is_file()
    assert path.name == "warden-fake-bin"
    assert path.stat().st_mode & stat.S_IXUSR
    assert os.environ["PATH"].split(os.pathsep)[0] == str(path.parent)
    assert Path(shutil.which("warden-fake-bin")).resolve() == path.resolve()
    result = subprocess.run(
        ["warden-fake-bin"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert result.stdout.strip() == "FAKE-CANARY"
