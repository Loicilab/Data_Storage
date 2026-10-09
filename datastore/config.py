"""Paths and defaults. Everything lives under %LOCALAPPDATA%\\DataStore unless DATASTORE_HOME is set."""
import os
import sys
from pathlib import Path

APP_NAME = "DataStore"
DEFAULT_PORT = 8765

DEFAULT_SETTINGS = {
    "copies": 2,               # every file is kept on this many accounts, on different providers when possible
    "trash_days": 30,          # trashed files are purged from every provider after this many days
    "reserve_fraction": 0.05,  # never fill an account beyond 95 %
    "rclone_path": "",
}


def web_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "datastore" / "web"
    return Path(__file__).resolve().parent / "web"


class Paths:
    def __init__(self, root: Path | None = None):
        if root is None:
            override = os.environ.get("DATASTORE_HOME")
            root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / APP_NAME
        self.root = root
        self.db = root / "catalog.sqlite3"
        self.staging = root / "staging"       # files waiting to reach all their copies
        self.thumbs = root / "thumbs"
        self.demo = root / "demo-remotes"     # local folders that pretend to be cloud accounts
        self.bin = root / "bin"               # downloaded rclone.exe
        self.rclone_config = root / "rclone.conf"
        for path in (self.root, self.staging, self.thumbs, self.bin):
            path.mkdir(parents=True, exist_ok=True)
