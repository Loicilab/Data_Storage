"""Background mirroring: placement, uploads with retry, verification, repair and trash purging."""
import hashlib
import mimetypes
import os
from pathlib import Path
import threading
import time

from . import rclone_tool
from .backends import make_backend
from .catalog import Catalog
from .config import Paths
from .thumbs import make_thumbnail

GiB = 1024 ** 3
ACCOUNT_REFRESH_SECONDS = 600
WORKERS = 2


def remote_root_key(folder, name):
    """Human-readable layout, so every provider holds a browsable copy even without this app."""
    return "DataStore" + ("" if folder == "/" else folder) + "/" + name


def mirrored_capacity(frees, copies):
    """Largest amount X that fits `copies` times when each copy must sit in a different pool."""
    frees = [max(0, f) for f in frees]
    if len(frees) < copies or copies <= 0:
        return 0
    low, high = 0.0, sum(frees) / copies
    for _ in range(60):
        middle = (low + high) / 2
        if sum(min(f, middle) for f in frees) >= copies * middle:
            low = middle
        else:
            high = middle
    return int(low)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Engine:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.catalog = Catalog(paths.db)
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.verifying = False
        self._file_locks = {}
        self._file_locks_guard = threading.Lock()
        self._warned_full = set()
        self._last_refresh = 0.0

    # -- lifecycle ---------------------------------------------------------------------------
    def start(self):
        for index in range(WORKERS):
            threading.Thread(target=self._worker, name=f"upload-{index}", daemon=True).start()
        threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True).start()

    def stop(self):
        self.stopping.set()
        self.wake.set()

    # -- helpers -----------------------------------------------------------------------------
    def rclone_exe(self):
        return rclone_tool.find(self.paths, self.catalog.setting("rclone_path"))

    def backend(self, account):
        return make_backend(account, self.rclone_exe(), self.paths.rclone_config)

    def staged_path(self, file_id):
        return self.paths.staging / str(file_id)

    def _lock_for(self, file_id):
        with self._file_locks_guard:
            return self._file_locks.setdefault(file_id, threading.Lock())

    # -- ingest ------------------------------------------------------------------------------
    def ingest(self, temp_path: Path, folder, name, size, sha256, modified_at):
        existing = self.catalog.find_live(folder, name)
        if existing and existing["sha256"] == sha256:
            temp_path.unlink(missing_ok=True)
            return {**existing, "duplicate": True}
        self.catalog.ensure_folder(folder)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        file_id = self.catalog.add_file(folder, name, size, sha256, mime, modified_at)
        staged = self.staged_path(file_id)
        os.replace(temp_path, staged)
        if make_thumbnail(staged, self.paths.thumbs / f"{file_id}.jpg", mime):
            self.catalog.set_thumb(file_id)
        self.ensure_placement(self.catalog.file(file_id))
        return self.catalog.file(file_id)

    # -- placement ---------------------------------------------------------------------------
    def choose_accounts(self, size, count, exclude_accounts=(), exclude_providers=()):
        reserve = self.catalog.setting("reserve_fraction")
        candidates = []
        for account in self.catalog.accounts():
            if not account["enabled"] or account["status"] == "error" or account["id"] in exclude_accounts:
                continue
            free = float("inf") if account["free"] is None else account["free"]
            available = free - account["reserved"] - reserve * (account["capacity"] or 0)
            if available >= size:
                candidates.append((available, account))
        candidates.sort(key=lambda item: item[0], reverse=True)
        chosen, providers = [], {p.lower() for p in exclude_providers}
        for _, account in candidates:  # first pass: one account per provider
            if len(chosen) < count and account["provider"].lower() not in providers:
                chosen.append(account)
                providers.add(account["provider"].lower())
        for _, account in candidates:  # fallback: same provider, different account
            if len(chosen) < count and account not in chosen:
                chosen.append(account)
        return chosen

    def ensure_placement(self, file):
        copies = self.catalog.setting("copies")
        existing = self.catalog.replicas(file["id"])
        missing = copies - len(existing)
        if missing <= 0:
            return
        chosen = self.choose_accounts(file["size"], missing,
                                      exclude_accounts={r["account_id"] for r in existing},
                                      exclude_providers={r["provider"] for r in existing})
        if len(chosen) < missing and file["id"] not in self._warned_full:
            self._warned_full.add(file["id"])
            have = len(existing) + len(chosen)
            self.catalog.log("warn", f"Only {have} of {copies} copies possible for “{file['name']}” - add an account with free space")
        for account in chosen:
            key = remote_root_key(file["folder"], file["name"])
            if self.catalog.key_taken(account["id"], key):
                stem, ext = os.path.splitext(key)
                key = f"{stem}~{file['id']}{ext}"
            self.catalog.add_replica(file["id"], account["id"], key)
        if chosen:
            self._warned_full.discard(file["id"])
            self.wake.set()

    # -- uploads -----------------------------------------------------------------------------
    def _worker(self):
        while not self.stopping.is_set():
            job = self.catalog.claim_job()
            if job is None:
                self.wake.wait(3)
                self.wake.clear()
                continue
            self._upload(job)

    def _materialize(self, file, exclude_account):
        """Local copy of a file: the staged upload, or a download from a healthy replica (repair)."""
        staged = self.staged_path(file["id"])
        with self._lock_for(file["id"]):
            if staged.exists():
                return staged
            for replica in self.catalog.ok_replicas(file["id"]):
                if replica["account_id"] == exclude_account:
                    continue
                partial = staged.with_suffix(".download")
                try:
                    self.backend(self.catalog.account(replica["account_id"])).download(replica["remote_key"], partial)
                    if sha256_of(partial) != file["sha256"]:
                        raise RuntimeError("checksum mismatch")
                    os.replace(partial, staged)
                    return staged
                except Exception as error:
                    partial.unlink(missing_ok=True)
                    self.catalog.log("warn", f"Copy of “{file['name']}” on {replica['label']} unusable for repair: {error}")
            raise RuntimeError("no healthy copy available to repair from")

    def _upload(self, job):
        file = self.catalog.file(job["file_id"])
        account = self.catalog.account(job["account_id"])
        if file is None or account is None:
            return
        try:
            source = self._materialize(file, exclude_account=account["id"])
            backend = self.backend(account)
            backend.upload(source, job["remote_key"])
            size = backend.stat(job["remote_key"])
            if size != file["size"]:
                raise RuntimeError(f"size check failed after upload ({size} of {file['size']} bytes)")
            self.catalog.replica_done(job["id"], account["id"], file["size"])
        except Exception as error:
            attempts = job["attempts"] + 1
            self.catalog.replica_failed(job["id"], str(error)[:500], attempts)
            if attempts in (1, 5):
                self.catalog.log("error", f"Upload of “{file['name']}” to {account['label']} failed (attempt {attempts}): {error}")
            return
        copies = self.catalog.setting("copies")
        if file["id"] in self.catalog.complete_file_ids(copies):
            labels = " + ".join(r["label"] for r in self.catalog.ok_replicas(file["id"]))
            self.catalog.log("ok", f"“{file['name']}” protected on {labels}")
            self._drop_staged(file["id"])

    def _drop_staged(self, file_id):
        try:
            self.staged_path(file_id).unlink(missing_ok=True)
        except PermissionError:
            pass  # being streamed to the browser right now; housekeeping retries later

    # -- housekeeping ------------------------------------------------------------------------
    def _housekeeping(self):
        while not self.stopping.is_set():
            try:
                if time.time() - self._last_refresh > ACCOUNT_REFRESH_SECONDS:
                    self.refresh_accounts()
                copies = self.catalog.setting("copies")
                for file in self.catalog.under_replicated(copies):
                    if file["id"] not in self._warned_full:
                        self.ensure_placement(file)
                self.purge(self.catalog.expired_trash(time.time() - self.catalog.setting("trash_days") * 86400))
                for file_id in self.catalog.complete_file_ids(copies):
                    if self.staged_path(file_id).exists():
                        self._drop_staged(file_id)
            except Exception as error:
                self.catalog.log("error", f"Housekeeping error: {error}")
            self.stopping.wait(15)

    def refresh_account(self, account):
        try:
            info = self.backend(account).about()
            self.catalog.update_account(account["id"], capacity=info["total"], used=info["used"], free=info["free"],
                                        status="ok", error=None, last_seen=time.time())
        except Exception as error:
            self.catalog.update_account(account["id"], status="error", error=str(error)[:400])

    def refresh_accounts(self):
        self._last_refresh = time.time()
        for account in self.catalog.accounts():
            self.refresh_account(account)
        self._warned_full.clear()  # space may have appeared; try placement again

    def add_account(self, label, provider, kind, target, capacity=None):
        candidate = {"kind": kind, "target": target, "capacity": capacity}
        info = self.backend(candidate).about()  # raises when the connection does not work
        account_id = self.catalog.add_account(label, provider, kind, target, capacity)
        self.catalog.update_account(account_id, capacity=info["total"], used=info["used"], free=info["free"],
                                    status="ok", last_seen=time.time())
        self.catalog.log("ok", f"Connected {label} ({provider})")
        self._warned_full.clear()
        return account_id

    def remove_account(self, account_id):
        account = self.catalog.account(account_id)
        affected = self.catalog.remove_account(account_id)
        self.catalog.log("warn", f"Removed {account['label']}; {affected} copies will be re-created on other accounts")
        self._warned_full.clear()

    def create_demo(self):
        demo = [("MEGA (demo)", "MEGA demo 1", 20), ("MEGA (demo)", "MEGA demo 2", 20),
                ("Blomp (demo)", "Blomp demo 1", 40), ("Blomp (demo)", "Blomp demo 2", 40)]
        for provider, label, gigabytes in demo:
            folder = self.paths.demo / label.lower().replace(" ", "-")
            folder.mkdir(parents=True, exist_ok=True)
            self.add_account(label, provider, "local", str(folder), gigabytes * GiB)

    # -- verification and deletion -----------------------------------------------------------
    def verify_all(self):
        if self.verifying:
            return
        self.verifying = True
        self.catalog.log("info", "Verifying every stored copy…")

        def run():
            checked = missing = 0
            try:
                backends = {}
                for replica in self.catalog.all_ok_replicas():
                    account = self.catalog.account(replica["account_id"])
                    try:
                        backend = backends.setdefault(account["id"], self.backend(account))
                        size = backend.stat(replica["remote_key"])
                    except Exception as error:
                        self.catalog.log("error", f"Could not check {account['label']}: {error}")
                        continue
                    checked += 1
                    if size != replica["size"]:
                        missing += 1
                        self.catalog.replica_missing(replica["id"], "missing or damaged - re-uploading")
                        self.catalog.log("warn", f"Copy of “{replica['name']}” on {account['label']} is missing or damaged; repairing")
                    else:
                        self.catalog.replica_verified(replica["id"])
                self.catalog.retry_failed()
                level = "ok" if missing == 0 else "warn"
                self.catalog.log(level, f"Verification finished: {checked} copies checked, {missing} need repair")
            finally:
                self.verifying = False
                self.wake.set()

        threading.Thread(target=run, name="verify", daemon=True).start()

    def purge(self, files):
        for file in files:
            for replica in self.catalog.replicas(file["id"]):
                try:
                    self.backend(self.catalog.account(replica["account_id"])).delete(replica["remote_key"])
                except Exception as error:
                    self.catalog.log("warn", f"Could not delete “{file['name']}” from {replica['label']}: {error}")
            self.catalog.forget_file(file["id"])
            self._drop_staged(file["id"])
            (self.paths.thumbs / f"{file['id']}.jpg").unlink(missing_ok=True)
        if files:
            self.catalog.log("info", f"Permanently deleted {len(files)} file(s) from trash")

    def empty_trash(self):
        files = self.catalog.trashed()
        threading.Thread(target=self.purge, args=(files,), name="purge", daemon=True).start()
        return len(files)

    # -- dashboard ---------------------------------------------------------------------------
    def storage_overview(self):
        copies = self.catalog.setting("copies")
        accounts = self.catalog.accounts()
        pools = {}
        for account in accounts:
            pool = pools.setdefault(account["provider"].lower(), {"provider": account["provider"], "accounts": 0,
                                                                  "capacity": 0, "used": 0, "free": 0, "unknown": False})
            pool["accounts"] += 1
            if account["capacity"] is None or account["status"] == "error":
                pool["unknown"] = True
                continue
            pool["capacity"] += account["capacity"]
            pool["used"] += account["used"] or 0
            pool["free"] += max(0, (account["free"] or 0) - account["reserved"])
        pools = sorted(pools.values(), key=lambda p: p["provider"].lower())
        if len(pools) >= copies:
            usable = mirrored_capacity([p["free"] for p in pools], copies)
        else:
            usable = mirrored_capacity([max(0, (a["free"] or 0) - a["reserved"]) for a in accounts
                                        if a["status"] != "error"], copies)
        return {"accounts": accounts, "pools": pools, "usable_free": usable,
                "raw_capacity": sum(p["capacity"] for p in pools), "raw_free": sum(p["free"] for p in pools)}
