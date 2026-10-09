"""Entry point for the Android app: the same engine and web UI, running inside the app process."""
import os
from pathlib import Path
import threading

from . import netproxy
from .config import Paths
from .engine import Engine
from .server import make_server

_url = None
_lock = threading.Lock()


def start(files_dir, rclone_path, cache_dir):
    """Start everything once per process; returns the local URL for the app's WebView."""
    global _url
    with _lock:
        if _url:
            return _url
        proxy = netproxy.start()
        os.environ.update({
            "DATASTORE_RCLONE": rclone_path,
            "HOME": files_dir,                     # rclone keeps its cache under $HOME / XDG dirs
            "XDG_CACHE_HOME": cache_dir,
            "TMPDIR": cache_dir,
            "HTTPS_PROXY": proxy,
            "HTTP_PROXY": proxy,
            "NO_PROXY": "localhost,127.0.0.1",
            "RCLONE_MEGA_USE_HTTPS": "true",       # keep MEGA transfers on encrypted tunnels too
            # rclone (a Linux build) does not know Android's certificate store locations;
            # Android 14+ keeps the updatable store in the Conscrypt APEX.
            "SSL_CERT_DIR": "/apex/com.android.conscrypt/cacerts:/system/etc/security/cacerts",
        })
        engine = Engine(Paths(Path(files_dir) / "datastore"))
        server = make_server(engine, 0)
        engine.start()
        threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
        _url = f"http://127.0.0.1:{server.server_address[1]}/"
        return _url
