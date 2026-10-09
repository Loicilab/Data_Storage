"""Fetch the provider-recommended official CLI release into a task-specific directory."""
import hashlib
import json
from pathlib import Path
import requests
import sys

directory = Path(r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools")
response = requests.get("https://api.github.com/repos/FilenCloudDienste/filen-cli/releases/tags/v0.0.36",timeout=30)
response.raise_for_status()
release = response.json()
assets = [{"name":a["name"],"url":a["browser_download_url"],"size":a["size"],"digest":a.get("digest")} for a in release["assets"]]
manifest = {"version":release["tag_name"],"assets":assets}
(directory / "filen-cli-release.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(manifest,indent=2))
if "--download" in sys.argv:
    asset = next(a for a in assets if a["name"] == "filen-cli-v0.0.36-win-x64.exe")
    target = directory / asset["name"]
    if not target.exists():
        with requests.get(asset["url"],stream=True,timeout=30) as download:
            download.raise_for_status()
            with target.open("wb") as handle:
                for chunk in download.iter_content(1024*1024):
                    handle.write(chunk)
    digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    if target.stat().st_size != asset["size"] or digest != asset["digest"]:
        raise RuntimeError("Downloaded CLI failed verification; will not execute")
    print(json.dumps({"downloaded":str(target),"size":target.stat().st_size,"sha256_verified":True}))
