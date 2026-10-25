from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    configured = os.environ.get("SKILL_WARDEN_HOME")
    if configured:
        return Path(configured)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "skill-warden"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "skill-warden"
        return Path.home() / "AppData" / "Local" / "skill-warden"
    return Path.home() / ".local" / "share" / "skill-warden"
