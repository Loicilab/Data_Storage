"""Download the official portable rclone and verify its published checksum."""
import hashlib
import io
from pathlib import Path
import requests
import zipfile

base = "https://downloads.rclone.org/v1.75.2/"
filename = "rclone-v1.75.2-windows-amd64.zip"
destination = Path(r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools\rclone.exe")
if not destination.exists():
    response = requests.get(base + filename, timeout=90)
    response.raise_for_status()
    sums = requests.get(base + "SHA256SUMS", timeout=30)
    sums.raise_for_status()
    expected = next(line.split()[0] for line in sums.text.splitlines() if line.endswith(filename))
    actual = hashlib.sha256(response.content).hexdigest()
    if actual != expected:
        raise RuntimeError("Download checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        member = next(name for name in archive.namelist() if name.endswith("/rclone.exe"))
        destination.write_bytes(archive.read(member))
    print("Downloaded official rclone v1.75.2; SHA-256 matched published checksum.", flush=True)
else:
    print("Portable rclone already downloaded for this test.", flush=True)
