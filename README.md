# Data Store

One library for pictures and documents spread over several free cloud accounts.
Every file is kept on **two different providers** (for example MEGA and Blomp),
checked after upload, and rebuilt from the other copy if one goes missing.

## Run it

```
python -m datastore            # from source (Python 3.12+, Pillow optional for thumbnails)
dist\DataStore.exe             # or the packaged single-file app
```

The UI opens at <http://127.0.0.1:8765>. The console window shows the address;
closing it stops the app. Unfinished uploads resume on the next start.

The first screen offers **demo accounts**: four local folders that act like
MEGA 20 GB ×2 and Blomp 40 GB ×2, so everything can be tried without real logins.

## Connecting real accounts

1. **Accounts → Download rclone.** This downloads the official build and verifies its SHA-256 checksum.
2. **Open rclone setup.** Create a remote per account, e.g. `mega1` (type `mega`),
   `blomp1` (type `swift`), `gdrive1` (type `drive`).
   For encryption, create a `crypt` remote on top of each one and use that instead.
3. **Add account.** Pick the remote and give it a provider name. Accounts with the
   same provider name form one pool, and the two copies of a file always land in different pools.

## Why a local app, not a website

- Logins stay on this PC (`%LOCALAPPDATA%\DataStore\rclone.conf`); nothing is hosted.
- rclone is a native program; a browser page cannot run it, and most provider APIs block browser calls.
- Mirroring, retries and repair need a process that keeps running.
- The UI is still a web page, so it can later be reached from a phone (e.g. over Tailscale).

## How it works

| Piece | File |
|---|---|
| HTTP API + static UI, bound to 127.0.0.1, session cookie and Host check | `datastore/server.py` |
| Catalogue (files, copies, accounts, activity) in SQLite | `datastore/catalog.py` |
| Placement, upload workers, retry with back-off, verify and repair, trash purge | `datastore/engine.py` |
| Backends: rclone remote or local folder | `datastore/backends.py` |
| Web UI (no build step) | `datastore/web/` |

- Files are stored under their real paths, e.g. `DataStore/Photos/2026/IMG_4100.jpg`,
  so each provider holds a browsable copy even without this app.
- An upload is first saved locally, hashed (SHA-256), then copied to the account
  with the most free space at each of two providers. The local copy is deleted once both copies are confirmed.
- **Verify all copies** (Activity) re-checks every copy. Missing or damaged ones are
  re-uploaded from the healthy copy, and downloads are hash-checked before reuse.
- Removing an account re-creates its copies elsewhere.
- Deleted files stay in Trash for 30 days before they are removed from providers.

## Android app

The phone runs **the same app**, with no server or VPN in between: the same Python engine and web UI
run inside the app (via [Chaquopy](https://chaquo.com/chaquopy/)), and the app bundles the official rclone
Linux ARM64 build. Uploads go straight from the phone to the providers.

- **Logins:** set accounts up on the PC, click **Accounts → Export logins**, copy the file to the phone
  over USB, then use **Import logins** in the app. Delete the copied file afterwards.
- **rclone networking:** Android has no `/etc/resolv.conf`, so rclone cannot look up host names by itself.
  `datastore/netproxy.py` is a password-protected relay on 127.0.0.1 that rclone uses through
  `HTTPS_PROXY`, and Python resolves names with Android's own resolver.
- **Thumbnails** come from Android's built-in image and video decoders, including HEIC.

Build (JDK 17 and the Android SDK; Gradle comes from the wrapper):

```
cd android
python fetch_rclone.py              # official rclone arm64 build, SHA-256 checked
gradlew assembleDebug               # -> app/build/outputs/apk/debug/app-debug.apk
```

Install on the phone by copying the APK over (allow "install unknown apps" once), or with `adb install`.

## Build the exe

```
python -m venv .venv
.venv\Scripts\pip install pyinstaller pillow
.venv\Scripts\python build_exe.py      # -> dist\DataStore.exe
```

## Not done yet

- **Accounts as the source of truth:** today each device keeps its own catalogue, so the phone only
  lists what was uploaded from the phone. Next step: every device reads the file list from the providers on start.
- Phone: keep uploading when the app is in the background (foreground service), QR-code login transfer instead of USB
- Backing up the catalogue itself to the providers (the readable file layout makes a rebuild possible, but there is no "rescan" yet)
- Rename/move, folder delete with contents, scheduled verification
- Tray icon / autostart, and remote access from the phone
- Guided in-app login forms instead of the rclone setup console
