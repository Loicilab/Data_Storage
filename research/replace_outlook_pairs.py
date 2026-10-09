"""Update proposed addresses only; creates no provider accounts."""
import json
import secrets
from cloud_signup_execute import load_vault, save_vault
from permanent_email_pairs import KEY, DEST, pair_csv_rows

def update_pairs():
    vault = load_vault()
    batch = vault[KEY]
    used = {p["b"]["email"].split("@")[0].lower() for p in batch["pairs"]}
    for pair in batch["pairs"]:
        if pair["a"]["provider"] == "Mailfence":
            used.add(pair["a"]["email"].split("@")[0].lower())
            continue
        old = pair["a"]
        if old["status"] == "created":
            raise RuntimeError("Cannot replace a registered inbox proposal")
        while True:
            local = pair["last_name"].lower() + pair["first_name"].lower() + str(1000+secrets.randbelow(9000))
            if local not in used:
                used.add(local)
                break
        pair.setdefault("retired_email_proposals", []).append({"email":old["email"], "provider":old["provider"], "status":old["status"]})
        pair["a"] = {"provider":"Mailfence", "email":local+"@mailfence.com", "password":old["password"], "status":"planned"}
        if pair["mega"]["status"] == "not_created":
            pair["mega"]["email"] = pair["a"]["email"]
    batch["provider_selection"] = "Mailfence and Proton, different providers and different usernames per pair"
    save_vault(vault)
    records = pair_csv_rows(batch)
    public_rows = [{k:v for k,v in r.items() if k not in {"password_a","password_b"}} for r in records]
    manifest = json.loads((DEST / "email-pairs.json").read_text(encoding="utf-8"))
    manifest["pairs"] = public_rows
    manifest["notice"] = "Proposed addresses have not been registered or checked for availability. Pairing does not configure recovery or copy files."
    (DEST / "email-pairs.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return records

if __name__ == "__main__":
    print(json.dumps([{k:v for k,v in r.items() if not k.startswith("password_")} for r in update_pairs()], indent=2))
