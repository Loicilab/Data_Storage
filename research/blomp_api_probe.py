"""Public discovery only; does not transmit account credentials."""
import json
from pathlib import Path
import requests

results = []
for url in ["https://authenticate.blomp.com", "https://authenticate.ain.net"]:
    response = requests.get(url, timeout=20)
    record = {"url": url, "http_status": response.status_code}
    try:
        payload = response.json()
        versions = payload.get("versions", {})
        items = versions.get("values", []) if isinstance(versions, dict) else versions
        if not items and "version" in payload:
            items = [payload["version"]]
        record["advertised_api_versions"] = [item.get("id") for item in items]
    except ValueError:
        record["json_response"] = False
    results.append(record)

report = {
    "provider": "blomp", "test_date": "2026-10-09",
    "signup_status": "not completed: image CAPTCHA rejected completed attempts",
    "authenticated_file_test": "not run: no activated account",
    "public_discovery": results,
}
output = Path(__file__).parent / "signup-evidence" / "blomp-api-discovery.json"
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
