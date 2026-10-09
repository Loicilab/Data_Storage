"""Locate, download (checksum-verified) and configure the official rclone binary."""
import configparser
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from .backends import NO_WINDOW

VERSION = "v1.75.2"
BASE_URL = f"https://downloads.rclone.org/{VERSION}/"
ARCHIVE = f"rclone-{VERSION}-windows-amd64.zip"
ON_WINDOWS = os.name == "nt"


def find(paths, configured=""):
    # The Android app ships its own rclone and announces it through DATASTORE_RCLONE.
    candidates = [os.environ.get("DATASTORE_RCLONE"), configured, paths.bin / "rclone.exe",
                  Path(sys.executable).parent / "rclone.exe", shutil.which("rclone")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def capabilities():
    """What the Accounts page may offer on this device."""
    bundled = bool(os.environ.get("DATASTORE_RCLONE"))
    return {
        "platform": "android" if bundled else sys.platform,
        "can_download": ON_WINDOWS and not bundled,
        "can_configure": ON_WINDOWS and not bundled,  # interactive setup needs a console window
    }


def download(paths):
    if not ON_WINDOWS:
        raise RuntimeError("rclone is built into the app on this device")

    def fetch(url, timeout):
        request = urllib.request.Request(url, headers={"User-Agent": "DataStore"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    archive = fetch(BASE_URL + ARCHIVE, 180)
    sums = fetch(BASE_URL + "SHA256SUMS", 30).decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.strip().endswith(ARCHIVE))
    if hashlib.sha256(archive).hexdigest() != expected:
        raise RuntimeError("Downloaded rclone does not match its published SHA-256 checksum")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        member = next(name for name in bundle.namelist() if name.endswith("/rclone.exe"))
        destination = paths.bin / "rclone.exe"
        destination.write_bytes(bundle.read(member))
    return destination


def list_remotes(exe, config):
    """Remote names from the config file; only a password-encrypted config needs rclone itself."""
    config = Path(config)
    if not config.is_file():
        return []
    text = config.read_text(encoding="utf-8", errors="replace")
    if "RCLONE_ENCRYPT_V0:" not in text:
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(text)
            return [name for name in parser.sections() if parser.has_option(name, "type")]
        except configparser.Error:
            pass
    if not exe:
        return []
    output = subprocess.run([str(exe), "--config", str(config), "listremotes"], capture_output=True, text=True,
                            timeout=30, creationflags=NO_WINDOW).stdout
    return [line.strip().rstrip(":") for line in output.splitlines() if line.strip()]


def import_config(paths, text):
    """Install an rclone.conf exported from another device; returns the remote names it contains."""
    if len(text) > 1_000_000:
        raise ValueError("That file is too large to be an rclone config")
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error as error:
        raise ValueError(f"Not a valid rclone config: {error}") from None
    remotes = [name for name in parser.sections() if parser.has_option(name, "type")]
    if not remotes:
        raise ValueError("No rclone remotes found in that file")
    partial = paths.rclone_config.with_suffix(".partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, paths.rclone_config)
    return remotes


def open_config_console(exe, config):
    """rclone's interactive setup (logins, Google OAuth, encryption) in its own console window."""
    if not ON_WINDOWS:
        raise RuntimeError("Interactive setup is only available on the PC")
    subprocess.Popen([str(exe), "--config", str(config), "config"], creationflags=subprocess.CREATE_NEW_CONSOLE)
