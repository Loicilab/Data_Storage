"""Local HTTP server: JSON API + static web UI. Binds to 127.0.0.1 only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import secrets
import shutil
import time
from urllib.parse import parse_qs, quote, urlsplit

from . import rclone_tool
from .config import web_root

FORBIDDEN_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

ROUTES = [
    ("GET", r"/api/state", "state"),
    ("GET", r"/api/list", "list"),
    ("GET", r"/api/search", "search"),
    ("GET", r"/api/photos", "photos"),
    ("POST", r"/api/folders", "create_folder"),
    ("DELETE", r"/api/folders", "delete_folder"),
    ("PUT", r"/api/upload", "upload"),
    ("GET", r"/api/files/(\d+)", "file"),
    ("GET", r"/api/files/(\d+)/content", "content"),
    ("GET", r"/api/files/(\d+)/thumb", "thumb"),
    ("DELETE", r"/api/files/(\d+)", "trash_file"),
    ("POST", r"/api/files/(\d+)/restore", "restore"),
    ("GET", r"/api/trash", "trash"),
    ("POST", r"/api/trash/empty", "empty_trash"),
    ("POST", r"/api/accounts", "add_account"),
    ("DELETE", r"/api/accounts/(\d+)", "remove_account"),
    ("POST", r"/api/accounts/refresh", "refresh_accounts"),
    ("POST", r"/api/demo", "demo"),
    ("POST", r"/api/verify", "verify"),
    ("GET", r"/api/activity", "activity"),
    ("GET", r"/api/rclone", "rclone"),
    ("POST", r"/api/rclone/download", "rclone_download"),
    ("POST", r"/api/rclone/configure", "rclone_configure"),
    ("POST", r"/api/rclone/import", "rclone_import"),
    ("GET", r"/api/rclone/export", "rclone_export"),
]


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def clean_name(name):
    name = FORBIDDEN_NAME_CHARS.sub("_", name).strip().strip(".")
    if not name:
        raise ApiError(400, "Invalid name")
    return name[:200]


def normalize_folder(path):
    parts = [p for p in (path or "/").replace("\\", "/").split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise ApiError(400, "Invalid folder")
    return "/" + "/".join(clean_name(p) for p in parts)


class Handler(BaseHTTPRequestHandler):
    server_version = "DataStore"
    protocol_version = "HTTP/1.1"

    @property
    def engine(self):
        return self.server.engine

    @property
    def catalog(self):
        return self.server.engine.catalog

    def log_message(self, *args):
        pass

    # -- dispatch ------------------------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        url = urlsplit(self.path)
        self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if self.headers.get("Host") not in self.server.allowed_hosts:
                raise ApiError(403, "Unexpected host")  # blocks DNS-rebinding pages
            if not url.path.startswith("/api/"):
                if method != "GET":
                    raise ApiError(405, "Method not allowed")
                return self._static(url.path)
            if self._cookie("ds_token") != self.server.token:
                raise ApiError(401, "Session expired - reload the page")
            for route_method, pattern, name in ROUTES:
                match = re.fullmatch(pattern, url.path)
                if match and route_method == method:
                    return getattr(self, "api_" + name)(*(int(g) for g in match.groups()))
            raise ApiError(404, "Not found")
        except ApiError as error:
            self.close_connection = True  # the request body may be partly unread
            self._json({"error": str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as error:  # noqa: BLE001 - report to the UI instead of dropping the connection
            self.close_connection = True
            self._json({"error": f"{type(error).__name__}: {error}"}, 500)

    # -- response helpers ----------------------------------------------------------------------
    def _cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return value
        return None

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length))

    def _json(self, data, status=200):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _static(self, path):
        root = web_root().resolve()
        target = (root / (path.lstrip("/") or "index.html")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            target = root / "index.html"  # single-page app fallback
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if target.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        if target.name == "index.html":
            self.send_header("Set-Cookie", f"ds_token={self.server.token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def _send_path(self, path, mime, name, download):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if match and size:
            first, last = match.groups()
            if first:
                start, end = int(first), min(int(last), size - 1) if last else size - 1
            elif last:
                start = max(0, size - int(last))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            status = 206
        self.send_response(status)
        self._content_headers(mime, name, download, end - start + 1)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as handle:
            handle.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = handle.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _content_headers(self, mime, name, download, length):
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(length))
        disposition = "attachment" if download else "inline"
        fallback = re.sub(r'[^\x20-\x7e]|["\\]', "_", name)  # for clients that ignore filename*
        self.send_header("Content-Disposition", f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}")
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")

    # -- API: overview -------------------------------------------------------------------------
    def api_state(self):
        overview = self.engine.storage_overview()
        self._json({
            "revision": self.catalog.revision,
            "copies": self.catalog.setting("copies"),
            "trash_days": self.catalog.setting("trash_days"),
            "summary": self.catalog.summary(self.catalog.setting("copies")),
            "verifying": self.engine.verifying,
            **overview,
        })

    def api_activity(self):
        self._json({"events": self.catalog.events()})

    def api_verify(self):
        self.engine.verify_all()
        self._json({"ok": True})

    # -- API: browsing -------------------------------------------------------------------------
    def api_list(self):
        folder = normalize_folder(self.query.get("folder"))
        if not self.catalog.folder_exists(folder):
            raise ApiError(404, "Folder not found")
        self._json({"folder": folder, "folders": self.catalog.subfolders(folder), "files": self.catalog.list_folder(folder)})

    def api_search(self):
        query = (self.query.get("q") or "").strip()
        self._json({"query": query, "files": self.catalog.search(query) if query else []})

    def api_photos(self):
        self._json({"files": self.catalog.photos()})

    def api_create_folder(self):
        path = normalize_folder(self._body().get("path"))
        if path == "/":
            raise ApiError(400, "Folder name required")
        self.catalog.ensure_folder(path)
        self._json({"path": path}, 201)

    def api_delete_folder(self):
        path = normalize_folder(self.query.get("path"))
        if path == "/":
            raise ApiError(400, "Cannot delete the root folder")
        try:
            self.catalog.delete_folder(path)
        except ValueError as error:
            raise ApiError(409, str(error))
        self._json({"ok": True})

    # -- API: files ----------------------------------------------------------------------------
    def api_upload(self):
        folder = normalize_folder(self.query.get("folder"))
        name = clean_name(self.query.get("name") or "")
        length = int(self.headers.get("Content-Length") or -1)
        if length < 0:
            raise ApiError(411, "Content-Length required")
        modified = float(self.query.get("mtime") or time.time())
        incoming = self.engine.paths.staging / f"incoming-{secrets.token_hex(8)}"
        digest, remaining = hashlib.sha256(), length
        try:
            with open(incoming, "wb") as out:
                while remaining:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        raise ApiError(400, "Upload interrupted")
                    digest.update(chunk)
                    out.write(chunk)
                    remaining -= len(chunk)
            result = self.engine.ingest(incoming, folder, name, length, digest.hexdigest(), modified)
        finally:
            incoming.unlink(missing_ok=True)
        self._json(result, 201)

    def _file_or_404(self, file_id):
        file = self.catalog.file(file_id)
        if file is None:
            raise ApiError(404, "File not found")
        return file

    def api_file(self, file_id):
        file = self._file_or_404(file_id)
        file["replicas"] = self.catalog.replicas(file_id)
        file["staged"] = self.engine.staged_path(file_id).exists()
        file["copies_wanted"] = self.catalog.setting("copies")
        self._json(file)

    def api_thumb(self, file_id):
        path = self.engine.paths.thumbs / f"{file_id}.jpg"
        if not path.is_file():
            raise ApiError(404, "No thumbnail")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=604800, immutable")
        self.end_headers()
        self.wfile.write(body)

    def api_content(self, file_id):
        file = self._file_or_404(file_id)
        download = self.query.get("download") == "1"
        staged = self.engine.staged_path(file_id)
        if staged.is_file():
            return self._send_path(staged, file["mime"], file["name"], download)
        for replica in self.catalog.ok_replicas(file_id):
            try:
                backend = self.engine.backend(self.catalog.account(replica["account_id"]))
                local = backend.local_path(replica["remote_key"])
                if local is not None:
                    if local.is_file():
                        return self._send_path(local, file["mime"], file["name"], download)
                    continue
                stream = backend.open(replica["remote_key"])
            except Exception:
                continue
            try:
                first = stream.read(1 << 16)
                if not first and file["size"]:
                    continue  # this provider failed; try the other copy
                self.send_response(200)
                self._content_headers(file["mime"], file["name"], download, file["size"])
                self.end_headers()
                self.wfile.write(first)
                shutil.copyfileobj(stream, self.wfile, 1 << 20)
                return
            finally:
                stream.close()
        raise ApiError(502, "No copy of this file is reachable right now")

    def api_trash_file(self, file_id):
        self._file_or_404(file_id)
        self.catalog.move_to_trash(file_id)
        self._json({"ok": True})

    def api_restore(self, file_id):
        self._file_or_404(file_id)
        self.catalog.restore(file_id)
        self._json(self.catalog.file(file_id))

    def api_trash(self):
        self._json({"files": self.catalog.trashed(), "trash_days": self.catalog.setting("trash_days")})

    def api_empty_trash(self):
        self._json({"purging": self.engine.empty_trash()})

    # -- API: accounts -------------------------------------------------------------------------
    def api_add_account(self):
        body = self._body()
        label = (body.get("label") or "").strip()
        provider = (body.get("provider") or "").strip()
        kind = body.get("kind")
        target = (body.get("target") or "").strip()
        if not label or not provider or not target or kind not in ("rclone", "local"):
            raise ApiError(400, "Label, provider and connection are required")
        capacity = None
        if kind == "local":
            if not Path(target).is_absolute():
                raise ApiError(400, "Use a full folder path, e.g. D:\\Backup")
            Path(target).mkdir(parents=True, exist_ok=True)
            if body.get("capacity_gb"):
                capacity = int(float(body["capacity_gb"]) * 1024 ** 3)
        try:
            account_id = self.engine.add_account(label, provider, kind, target, capacity)
        except Exception as error:
            raise ApiError(400, f"Could not connect: {error}")
        self._json(self.catalog.account(account_id), 201)

    def api_remove_account(self, account_id):
        if self.catalog.account(account_id) is None:
            raise ApiError(404, "Account not found")
        self.engine.remove_account(account_id)
        self._json({"ok": True})

    def api_refresh_accounts(self):
        self.engine.refresh_accounts()
        self._json({"ok": True})

    def api_demo(self):
        self.engine.create_demo()
        self._json({"ok": True}, 201)

    def api_rclone(self):
        exe = self.engine.rclone_exe()
        self._json({"path": str(exe) if exe else None, "version": rclone_tool.VERSION,
                    "config": str(self.engine.paths.rclone_config),
                    "remotes": rclone_tool.list_remotes(exe, self.engine.paths.rclone_config),
                    **rclone_tool.capabilities()})

    def api_rclone_import(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length or length > 1_000_000:
            raise ApiError(400, "Choose an rclone.conf file")
        try:
            remotes = rclone_tool.import_config(self.engine.paths, self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise ApiError(400, str(error))
        self.catalog.log("ok", f"Imported logins for {len(remotes)} remote(s): {', '.join(remotes)}")
        self._json({"remotes": remotes})

    def api_rclone_export(self):
        config = self.engine.paths.rclone_config
        if not config.is_file():
            raise ApiError(404, "No logins set up yet")
        self.catalog.log("warn", "Logins exported for another device - delete the exported file once imported")
        self._send_path(config, "text/plain", "datastore-logins.conf", True)

    def api_rclone_download(self):
        if not rclone_tool.capabilities()["can_download"]:
            raise ApiError(409, "rclone is built into the app on this device")
        try:
            path = rclone_tool.download(self.engine.paths)
        except Exception as error:
            raise ApiError(502, f"Download failed: {error}")
        self.catalog.log("ok", f"Installed rclone {rclone_tool.VERSION} (checksum verified)")
        self._json({"path": str(path)})

    def api_rclone_configure(self):
        if not rclone_tool.capabilities()["can_configure"]:
            raise ApiError(409, "Set up logins on the PC, then import them here")
        exe = self.engine.rclone_exe()
        if not exe:
            raise ApiError(409, "Download rclone first")
        rclone_tool.open_config_console(exe, self.engine.paths.rclone_config)
        self._json({"ok": True})


def make_server(engine, port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)  # port 0 = any free port (Android app)
    server.daemon_threads = True
    server.engine = engine
    port = server.server_address[1]
    server.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    token = engine.catalog.setting("token")
    if not token:
        token = secrets.token_urlsafe(32)
        engine.catalog.set_setting("token", token)
    server.token = token
    return server
