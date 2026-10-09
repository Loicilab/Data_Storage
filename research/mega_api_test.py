"""Exercise MEGA through rclone without printing credentials or tokens."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import secrets
import argparse

from cloud_signup_execute import load_vault, OUT

RCLONE = Path(r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools\rclone.exe")
parser = argparse.ArgumentParser()
parser.add_argument("--vault-key", default="mega")
parser.add_argument("--evidence-name", default="mega-api-test")
options = parser.parse_args()
credentials = load_vault()[options.vault_key]
result = {"provider":"mega", "client":"rclone v1.75.2", "tests":[]}
environment = os.environ.copy()
environment.update({"RCLONE_CONFIG_TEST_MEGA_TYPE":"mega", "RCLONE_CONFIG_TEST_MEGA_USER": credentials["email"]})
obscured = subprocess.run([str(RCLONE), "obscure", credentials["password"]], capture_output=True, text=True, check=True).stdout.strip()
environment["RCLONE_CONFIG_TEST_MEGA_PASS"] = obscured

def call(args, binary=False):
    completed = subprocess.run([str(RCLONE), "--config", "NUL", "--retries", "1", "--low-level-retries", "1"] + args, env=environment, capture_output=True, timeout=60)
    if completed.returncode:
        error = completed.stderr.decode(errors="replace").replace(credentials["email"], "[TEST EMAIL]")
        raise RuntimeError(error[:2000])
    return completed.stdout if binary else completed.stdout.decode()

try:
    quota = json.loads(call(["about", "test_mega:", "--json"]))
    result["quota"] = quota
    result["tests"].append("Authenticated quota query passed")
    name = "integration-test-20261009-" + secrets.token_hex(5) + ".txt"
    local = OUT / name
    payload = b"Isolated cloud API integration test. No personal files.\n"
    local.write_bytes(payload)
    remote = "test_mega:" + name
    uploaded = False
    try:
        call(["copyto", str(local), remote])
        uploaded = True
        result["tests"].append("Upload passed")
        listed = json.loads(call(["lsjson", "test_mega:"]))
        if name not in {entry["Name"] for entry in listed}:
            raise RuntimeError("Uploaded file was not returned by listing")
        result["tests"].append("Listing passed")
        downloaded = call(["cat", remote], binary=True)
        if hashlib.sha256(downloaded).digest() != hashlib.sha256(payload).digest():
            raise RuntimeError("Downloaded bytes did not match upload")
        result["tests"].append("Download passed; SHA-256 matched original")
    finally:
        if uploaded:
            call(["deletefile", remote])
            result["tests"].append("Deleted only the generated test file")
    result["status"] = "passed"
except Exception as exc:
    result["status"] = "failed"
    result["error"] = str(exc)

(OUT / (options.evidence_name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2), flush=True)
