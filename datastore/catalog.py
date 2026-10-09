"""SQLite catalogue: one row per file, one row per remote copy (replica) of that file."""
from contextlib import contextmanager
import json
import os
import sqlite3
import threading
import time

from .config import DEFAULT_SETTINGS

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    provider TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 'rclone' or 'local'
    target TEXT NOT NULL,            -- rclone remote name, or folder path
    capacity INTEGER, used INTEGER, free INTEGER,
    status TEXT NOT NULL DEFAULT 'unknown',
    error TEXT,
    last_seen REAL,
    created_at REAL NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY, parent TEXT, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS folders_parent ON folders(parent);
CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY,
    folder TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    mime TEXT,
    modified_at REAL NOT NULL,
    created_at REAL NOT NULL,
    deleted_at REAL,
    has_thumb INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS files_live_path ON files(folder, name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS files_mime ON files(mime);
CREATE TABLE IF NOT EXISTS replicas(
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    remote_key TEXT NOT NULL,
    state TEXT NOT NULL,             -- pending | uploading | ok | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try REAL NOT NULL DEFAULT 0,
    error TEXT,
    verified_at REAL
);
CREATE INDEX IF NOT EXISTS replicas_file ON replicas(file_id);
CREATE INDEX IF NOT EXISTS replicas_state ON replicas(state, next_try);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
"""

FILE_COLUMNS = """f.*,
    (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state = 'ok') AS ok_copies,
    (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state IN ('pending', 'uploading')) AS pending_copies,
    (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state = 'failed') AS failed_copies"""


def file_status(row, copies):
    if row["ok_copies"] >= copies:
        return "protected"
    if row["pending_copies"]:
        return "syncing"
    return "attention"


class Catalog:
    def __init__(self, path):
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)
        # Uploads cut short by a crash or shutdown simply start again.
        self._db.execute("UPDATE replicas SET state = 'pending' WHERE state = 'uploading'")
        self._db.execute("INSERT OR IGNORE INTO folders(path, parent, created_at) VALUES ('/', NULL, ?)", (time.time(),))
        self.revision = 1

    # -- plumbing ---------------------------------------------------------------------------
    def _rows(self, sql, args=()):
        with self._lock:
            return [dict(row) for row in self._db.execute(sql, args).fetchall()]

    def _row(self, sql, args=()):
        rows = self._rows(sql, args)
        return rows[0] if rows else None

    def _write(self, sql, args=()):
        with self._lock:
            cursor = self._db.execute(sql, args)
            self.revision += 1
            return cursor

    @contextmanager
    def transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
            self.revision += 1

    def decorate(self, row):
        if row is not None:
            row["status"] = file_status(row, self.setting("copies"))
        return row

    # -- settings and activity log ------------------------------------------------------------
    def setting(self, key):
        row = self._row("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(row["value"]) if row else DEFAULT_SETTINGS.get(key)

    def set_setting(self, key, value):
        self._write("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)))

    def log(self, level, message):
        with self._lock:
            self._write("INSERT INTO events(at, level, message) VALUES (?, ?, ?)", (time.time(), level, message))
            self._db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) - 1000 FROM events)")

    def events(self, limit=200):
        return self._rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    # -- folders -------------------------------------------------------------------------------
    def ensure_folder(self, path):
        parts = [p for p in path.split("/") if p]
        with self._lock:
            parent = "/"
            for index in range(len(parts)):
                current = "/" + "/".join(parts[:index + 1])
                self._db.execute("INSERT OR IGNORE INTO folders(path, parent, created_at) VALUES (?, ?, ?)",
                                 (current, parent, time.time()))
                parent = current
            self.revision += 1

    def folder_exists(self, path):
        return self._row("SELECT 1 FROM folders WHERE path = ?", (path,)) is not None

    def subfolders(self, path):
        return self._rows("""
            SELECT d.path,
                   (SELECT COUNT(*) FROM files f WHERE f.folder = d.path AND f.deleted_at IS NULL) AS files,
                   (SELECT COUNT(*) FROM folders c WHERE c.parent = d.path) AS folders
            FROM folders d WHERE d.parent = ? ORDER BY d.path COLLATE NOCASE""", (path,))

    def delete_folder(self, path):
        with self.transaction() as db:
            busy = db.execute("""SELECT (SELECT COUNT(*) FROM folders WHERE parent = ?)
                                      + (SELECT COUNT(*) FROM files WHERE folder = ? AND deleted_at IS NULL)""",
                              (path, path)).fetchone()[0]
            if busy:
                raise ValueError("Only empty folders can be deleted")
            db.execute("DELETE FROM folders WHERE path = ?", (path,))

    # -- files ---------------------------------------------------------------------------------
    def _free_name(self, db, folder, name):
        stem, ext = os.path.splitext(name)
        candidate, number = name, 1
        while db.execute("SELECT 1 FROM files WHERE folder = ? AND name = ? AND deleted_at IS NULL",
                         (folder, candidate)).fetchone():
            number += 1
            candidate = f"{stem} ({number}){ext}"
        return candidate

    def add_file(self, folder, name, size, sha256, mime, modified_at):
        with self.transaction() as db:
            name = self._free_name(db, folder, name)
            cursor = db.execute("""INSERT INTO files(folder, name, size, sha256, mime, modified_at, created_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (folder, name, size, sha256, mime, modified_at, time.time()))
            return cursor.lastrowid

    def set_thumb(self, file_id):
        self._write("UPDATE files SET has_thumb = 1 WHERE id = ?", (file_id,))

    def find_live(self, folder, name):
        return self.decorate(self._row(f"SELECT {FILE_COLUMNS} FROM files f WHERE folder = ? AND name = ? AND deleted_at IS NULL",
                                       (folder, name)))

    def file(self, file_id):
        return self.decorate(self._row(f"SELECT {FILE_COLUMNS} FROM files f WHERE f.id = ?", (file_id,)))

    def list_folder(self, folder):
        rows = self._rows(f"SELECT {FILE_COLUMNS} FROM files f WHERE folder = ? AND deleted_at IS NULL ORDER BY name COLLATE NOCASE",
                          (folder,))
        return [self.decorate(row) for row in rows]

    def search(self, query, limit=300):
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self._rows(f"""SELECT {FILE_COLUMNS} FROM files f WHERE deleted_at IS NULL AND name LIKE ? ESCAPE '\\'
                              ORDER BY modified_at DESC LIMIT ?""", (pattern, limit))
        return [self.decorate(row) for row in rows]

    def photos(self, limit=5000):
        rows = self._rows(f"""SELECT {FILE_COLUMNS} FROM files f WHERE deleted_at IS NULL
                              AND (mime LIKE 'image/%' OR mime LIKE 'video/%')
                              ORDER BY modified_at DESC LIMIT ?""", (limit,))
        return [self.decorate(row) for row in rows]

    def trashed(self):
        rows = self._rows(f"SELECT {FILE_COLUMNS} FROM files f WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")
        return [self.decorate(row) for row in rows]

    def move_to_trash(self, file_id):
        self._write("UPDATE files SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (time.time(), file_id))

    def restore(self, file_id):
        row = self.file(file_id)
        if row is None or row["deleted_at"] is None:
            return
        self.ensure_folder(row["folder"])
        with self.transaction() as db:
            name = self._free_name(db, row["folder"], row["name"])
            db.execute("UPDATE files SET deleted_at = NULL, name = ? WHERE id = ?", (name, file_id))

    def expired_trash(self, cutoff):
        return self._rows("SELECT * FROM files WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))

    def forget_file(self, file_id):
        self._write("DELETE FROM files WHERE id = ?", (file_id,))

    def under_replicated(self, copies, limit=200):
        return self._rows("""SELECT f.* FROM files f
                             WHERE (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id) < ?
                             ORDER BY f.id LIMIT ?""", (copies, limit))

    def complete_file_ids(self, copies):
        rows = self._rows("""SELECT f.id FROM files f
                             WHERE (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state = 'ok') >= ?
                               AND NOT EXISTS (SELECT 1 FROM replicas r WHERE r.file_id = f.id AND r.state != 'ok')""",
                          (copies,))
        return {row["id"] for row in rows}

    # -- accounts ------------------------------------------------------------------------------
    def accounts(self):
        return self._rows("""
            SELECT a.*,
                   (SELECT COUNT(*) FROM replicas r WHERE r.account_id = a.id AND r.state = 'ok') AS stored_files,
                   (SELECT COALESCE(SUM(f.size), 0) FROM replicas r JOIN files f ON f.id = r.file_id
                     WHERE r.account_id = a.id AND r.state != 'ok') AS reserved
            FROM accounts a ORDER BY a.provider COLLATE NOCASE, a.label COLLATE NOCASE""")

    def account(self, account_id):
        return self._row("SELECT * FROM accounts WHERE id = ?", (account_id,))

    def add_account(self, label, provider, kind, target, capacity=None):
        cursor = self._write("""INSERT INTO accounts(label, provider, kind, target, capacity, created_at)
                                VALUES (?, ?, ?, ?, ?, ?)""", (label, provider, kind, target, capacity, time.time()))
        return cursor.lastrowid

    def update_account(self, account_id, **fields):
        columns = ", ".join(f"{name} = ?" for name in fields)
        self._write(f"UPDATE accounts SET {columns} WHERE id = ?", (*fields.values(), account_id))

    def remove_account(self, account_id):
        """Forget the account; its copies are re-created elsewhere by the sync engine."""
        with self.transaction() as db:
            affected = db.execute("SELECT COUNT(*) FROM replicas WHERE account_id = ?", (account_id,)).fetchone()[0]
            db.execute("DELETE FROM replicas WHERE account_id = ?", (account_id,))
            db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            return affected

    # -- replicas ------------------------------------------------------------------------------
    def replicas(self, file_id):
        return self._rows("""SELECT r.*, a.label, a.provider, a.kind FROM replicas r JOIN accounts a ON a.id = r.account_id
                             WHERE r.file_id = ? ORDER BY a.provider COLLATE NOCASE""", (file_id,))

    def ok_replicas(self, file_id):
        return [r for r in self.replicas(file_id) if r["state"] == "ok"]

    def all_ok_replicas(self):
        return self._rows("SELECT r.*, f.size, f.name FROM replicas r JOIN files f ON f.id = r.file_id WHERE r.state = 'ok'")

    def key_taken(self, account_id, key):
        return self._row("SELECT 1 FROM replicas WHERE account_id = ? AND remote_key = ?", (account_id, key)) is not None

    def add_replica(self, file_id, account_id, key):
        self._write("INSERT INTO replicas(file_id, account_id, remote_key, state) VALUES (?, ?, ?, 'pending')",
                    (file_id, account_id, key))

    def claim_job(self):
        with self.transaction() as db:
            row = db.execute("""SELECT r.* FROM replicas r JOIN accounts a ON a.id = r.account_id
                                WHERE r.state IN ('pending', 'failed') AND r.next_try <= ? AND a.enabled = 1
                                ORDER BY r.next_try, r.id LIMIT 1""", (time.time(),)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE replicas SET state = 'uploading' WHERE id = ?", (row["id"],))
            return dict(row)

    def replica_done(self, replica_id, account_id, size):
        now = time.time()
        with self.transaction() as db:
            db.execute("UPDATE replicas SET state = 'ok', error = NULL, attempts = 0, verified_at = ? WHERE id = ?",
                       (now, replica_id))
            db.execute("""UPDATE accounts SET used = used + ?, free = free - ?, last_seen = ?, status = 'ok', error = NULL
                          WHERE id = ?""", (size, size, now, account_id))

    def replica_failed(self, replica_id, error, attempts):
        delay = min(3600, 15 * 2 ** attempts)
        self._write("UPDATE replicas SET state = 'failed', error = ?, attempts = ?, next_try = ? WHERE id = ?",
                    (error, attempts, time.time() + delay, replica_id))

    def replica_verified(self, replica_id):
        self._write("UPDATE replicas SET verified_at = ? WHERE id = ?", (time.time(), replica_id))

    def replica_missing(self, replica_id, reason):
        self._write("UPDATE replicas SET state = 'pending', error = ?, next_try = 0 WHERE id = ?", (reason, replica_id))

    def retry_failed(self):
        self._write("UPDATE replicas SET next_try = 0 WHERE state = 'failed'")

    # -- dashboard -----------------------------------------------------------------------------
    def summary(self, copies):
        row = self._row("""
            SELECT COUNT(*) AS files, COALESCE(SUM(size), 0) AS bytes,
                   COALESCE(SUM(ok >= ?), 0) AS protected,
                   COALESCE(SUM(ok < ? AND pending > 0), 0) AS syncing,
                   COALESCE(SUM(ok < ? AND pending = 0), 0) AS attention
            FROM (SELECT f.size,
                         (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state = 'ok') AS ok,
                         (SELECT COUNT(*) FROM replicas r WHERE r.file_id = f.id AND r.state IN ('pending', 'uploading')) AS pending
                  FROM files f WHERE f.deleted_at IS NULL)""", (copies, copies, copies))
        row["trashed"] = self._row("SELECT COUNT(*) AS n FROM files WHERE deleted_at IS NOT NULL")["n"]
        row["queue"] = {r["state"]: r["n"] for r in self._rows(
            "SELECT state, COUNT(*) AS n FROM replicas WHERE state != 'ok' GROUP BY state")}
        return row
