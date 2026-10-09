"""Download the official rclone Linux builds the app bundles, verifying their published SHA-256.

    python fetch_rclone.py              # phones (arm64-v8a)
    python fetch_rclone.py x86_64       # emulator
"""
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datastore.rclone_tool import VERSION  # same rclone version as the PC app

PLATFORMS = {"arm64-v8a": "linux-arm64", "x86_64": "linux-amd64"}
BASE_URL = f"https://downloads.rclone.org/{VERSION}/"
JNI_LIBS = Path(__file__).resolve().parent / "app" / "src" / "main" / "jniLibs"


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DataStore-build"}), timeout=300) as response:
        return response.read()


def main(abis):
    sums = fetch(BASE_URL + "SHA256SUMS").decode()
    for abi in abis:
        archive_name = f"rclone-{VERSION}-{PLATFORMS[abi]}.zip"
        expected = next(line.split()[0] for line in sums.splitlines() if line.strip().endswith(archive_name))
        archive = fetch(BASE_URL + archive_name)
        if hashlib.sha256(archive).hexdigest() != expected:
            raise SystemExit(f"Checksum mismatch for {archive_name}")
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            member = next(name for name in bundle.namelist() if name.endswith("/rclone"))
            target = JNI_LIBS / abi / "librclone.so"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))
        print(f"{abi}: rclone {VERSION} ({PLATFORMS[abi]}) verified -> {target}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["arm64-v8a"])
