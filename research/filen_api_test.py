"""Authenticate through the official CLI and rclone without logging credentials."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from cloud_signup_execute import load_vault, save_vault, OUT

TOOLS = Path(r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools")
CLI = TOOLS / "filen-cli-v0.0.36-win-x64.exe"
RCLONE = TOOLS / "rclone.exe"
WORK = TOOLS / "filen-api-test-work"
WORK.mkdir(exist_ok=True)
credentials = load_vault()["filen"]
environment = os.environ.copy()
environment.update({"FILEN_EMAIL":credentials["email"], "FILEN_PASSWORD":credentials["password"], "FILEN_CLI_DATA_DIR":str(WORK / "client-data")})

result = {"provider":"filen", "test_date":"2026-10-09", "signup":"created and email-activated without CAPTCHA", "tests":[]}
def redact(message):
    for secret in [credentials["email"], credentials["password"], credentials.get("api_key", "")]:
        if secret:
            message = message.replace(secret,"[REDACTED]")
    return re.sub(r"\b[a-zA-Z0-9_-]{32,}\b","[REDACTED]",message)

def rclone(args, binary=False):
    response = subprocess.run([str(RCLONE),"--config","NUL","--retries","1","--low-level-retries","1","--timeout","20s"] + args,env=environment,cwd=WORK,capture_output=True,timeout=60)
    if response.returncode:
        raise RuntimeError(redact(response.stderr.decode(errors="replace"))[:2000])
    return response.stdout if binary else response.stdout.decode()

def obscure(value):
    return subprocess.run([str(RCLONE),"obscure",value],capture_output=True,text=True,check=True).stdout.strip()

try:
    exported = subprocess.run([str(CLI),"--skip-update","export-api-key"],cwd=WORK,env=environment,input="y\n",text=True,capture_output=True,timeout=90)
    result["cli_export"] = {"exit_code":exported.returncode,"stdout_characters":len(exported.stdout),"stderr_characters":len(exported.stderr),"created_files":[str(f.relative_to(WORK)) for f in WORK.rglob("*") if f.is_file()]}
    if exported.returncode:
        result["cli_error"] = redact(exported.stderr)[:1500]
        result["status"] = "CLI authentication failed"
    else:
        match = re.search(r"API Key for " + re.escape(credentials["email"]) + r": ([^\s\x1b]+)",exported.stdout)
        if not match:
            raise RuntimeError("API-key output did not match the documented CLI export format")
        credentials["api_key"] = match.group(1)
        data = load_vault()
        data["filen"]["api_key"] = credentials["api_key"]
        data["filen"].pop("cli_export_stdout",None)
        save_vault(data)
        result["tests"].append("Official CLI authenticated and exported account API key")
        print("CLI authentication passed; checking rclone quota and listing",flush=True)
        environment.update({
            "RCLONE_CONFIG_TEST_FILEN_TYPE":"filen",
            "RCLONE_CONFIG_TEST_FILEN_EMAIL":credentials["email"],
            "RCLONE_CONFIG_TEST_FILEN_PASSWORD":obscure(credentials["password"]),
            "RCLONE_CONFIG_TEST_FILEN_API_KEY":obscure(credentials["api_key"]),
        })
        result["quota"] = json.loads(rclone(["about","test_filen:","--json"]))
        result["tests"].append("Authenticated quota query passed")
        print(json.dumps({"quota":result["quota"]}),flush=True)
        listing = json.loads(rclone(["lsjson","test_filen:"]))
        result["listed_objects"] = len(listing)
        result["tests"].append("Authenticated listing passed")
        name = "filen-integration-test-20261009-" + secrets.token_hex(5) + ".txt"
        local = OUT / name
        payload = b"Isolated cloud API integration test. No personal files.\n"
        local.write_bytes(payload)
        remote = "test_filen:" + name
        uploaded = False
        try:
            try:
                rclone(["copyto",str(local),remote])
                uploaded = True
            except RuntimeError as exc:
                result["upload"] = "rejected"
                result["upload_error"] = str(exc)
                result["status"] = "read API passed; upload rejected"
            if uploaded:
                result["tests"].append("Upload passed")
                downloaded = rclone(["cat",remote],binary=True)
                if hashlib.sha256(downloaded).digest() != hashlib.sha256(payload).digest():
                    raise RuntimeError("Downloaded bytes did not match upload")
                result["tests"].append("Download passed; SHA-256 matched original")
                result["status"] = "file API passed"
        finally:
            if uploaded:
                rclone(["deletefile",remote])
                result["tests"].append("Deleted only the generated test object")
except subprocess.TimeoutExpired:
    result["status"] = "CLI authentication timed out"
except Exception as exc:
    result["status"] = "API test incomplete"
    result["error"] = redact(str(exc))

(OUT / "filen-api-test.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
print(json.dumps(result,indent=2),flush=True)
