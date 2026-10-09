"""Start Data Store: background mirroring + the web UI on http://127.0.0.1:8765."""
import argparse
from pathlib import Path
import webbrowser

from .config import DEFAULT_PORT, Paths
from .engine import Engine
from .server import make_server


def main():
    parser = argparse.ArgumentParser(prog="DataStore", description="One place for files mirrored across free cloud accounts.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--home", type=Path, help="data folder (default: %%LOCALAPPDATA%%\\DataStore)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    paths = Paths(args.home)
    engine = Engine(paths)
    try:
        server = make_server(engine, args.port)
    except OSError:
        print(f"Data Store already seems to be running - opening {url}")
        webbrowser.open(url)
        return
    engine.start()
    print(f"Data Store is running at {url}")
    print(f"Data folder: {paths.root}")
    print("Close this window (or press Ctrl+C) to stop. Unfinished uploads resume on next start.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        server.server_close()


if __name__ == "__main__":
    main()
