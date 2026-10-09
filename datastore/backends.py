"""Storage backends. Each account is either an rclone remote (real cloud) or a local folder (testing / demo)."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class BackendError(RuntimeError):
    pass


class LocalFolderBackend:
    """A folder on disk standing in for a cloud account, with a simulated quota."""

    def __init__(self, root, capacity=None):
        self.root = Path(root)
        self.capacity = capacity

    def _path(self, key):
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise BackendError("Key escapes the account folder")
        return path

    def about(self):
        if not self.root.is_dir():
            raise BackendError(f"Folder not found: {self.root}")
        used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        if self.capacity:
            return {"total": self.capacity, "used": used, "free": max(0, self.capacity - used)}
        disk = shutil.disk_usage(self.root)
        return {"total": used + disk.free, "used": used, "free": disk.free}

    def upload(self, source, key):
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        shutil.copyfile(source, partial)
        os.replace(partial, destination)

    def download(self, key, destination):
        shutil.copyfile(self._path(key), destination)

    def stat(self, key):
        path = self._path(key)
        return path.stat().st_size if path.is_file() else None

    def local_path(self, key):
        return self._path(key)

    def open(self, key):
        return open(self._path(key), "rb")

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


class _ProcessStream:
    """File-like wrapper around `rclone cat` stdout that cleans up the process on close."""

    def __init__(self, process):
        self.process = process

    def read(self, size=-1):
        return self.process.stdout.read(size)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.stdout.close()
        self.process.wait()


class RcloneBackend:
    """Any provider rclone supports (MEGA, Blomp/Swift, Google Drive, OneDrive, pCloud, ...)."""

    def __init__(self, exe, config, remote):
        if not exe:
            raise BackendError("rclone is not installed yet - download it on the Accounts page")
        self.exe = str(exe)
        self.config = str(config)
        self.remote = remote if ":" in remote else remote + ":"

    def _target(self, key):
        separator = "" if self.remote.endswith((":", "/")) else "/"
        return self.remote + separator + key

    def _command(self, *args):
        return [self.exe, "--config", self.config, "--retries", "2", "--low-level-retries", "3", *args]

    def _run(self, *args, timeout=120):
        process = subprocess.run(self._command(*args), capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
        if process.returncode:
            raise BackendError(_last_error(process.stderr), process.returncode)
        return process.stdout

    def about(self):
        try:
            data = json.loads(self._run("about", self.remote, "--json"))
            return {"total": data.get("total"), "used": data.get("used"), "free": data.get("free")}
        except BackendError as error:
            if "doesn't support" not in str(error) and "not supported" not in str(error):
                raise
        self._run("lsf", "--max-depth", "1", self.remote)  # quota unknown, but the login works
        return {"total": None, "used": None, "free": None}

    def upload(self, source, key):
        self._run("copyto", str(source), self._target(key), timeout=None)

    def download(self, key, destination):
        self._run("copyto", self._target(key), str(destination), timeout=None)

    def stat(self, key):
        try:
            return json.loads(self._run("lsjson", "--stat", self._target(key)))["Size"]
        except BackendError as error:
            if error.args[1:] in ((3,), (4,)) or "not found" in str(error).lower():
                return None
            raise

    def local_path(self, key):
        return None

    def open(self, key):
        process = subprocess.Popen(self._command("cat", self._target(key)), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return _ProcessStream(process)

    def delete(self, key):
        try:
            self._run("deletefile", self._target(key))
        except BackendError as error:
            if "not found" not in str(error).lower():
                raise


def _last_error(stderr):
    lines = [line.strip() for line in stderr.decode(errors="replace").splitlines() if line.strip()]
    message = lines[-1] if lines else "rclone failed"
    return re.sub(r"^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d\s+(?:[A-Z]+\s*:\s*)?", "", message)[:400]


def make_backend(account, rclone_exe, rclone_config):
    if account["kind"] == "local":
        return LocalFolderBackend(account["target"], account.get("capacity"))
    if account["kind"] == "rclone":
        return RcloneBackend(rclone_exe, rclone_config, account["target"])
    raise BackendError(f"Unknown account kind {account['kind']!r}")
