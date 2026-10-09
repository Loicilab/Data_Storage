"""Register the prepared pairs at Mail.tm after the user selects this provider."""
import json
import time
import requests
from cloud_signup_execute import load_vault, save_vault
from permanent_email_pairs import KEY, export_pairs

def save_entry(index, role, updates):
    vault = load_vault()
    vault[KEY]["pairs"][index][role].update(updates)
    save_vault(vault)
    export_pairs(vault[KEY])

def main():
    session = requests.Session()
    response = session.get("https://api.mail.tm/domains", timeout=20)
    response.raise_for_status()
    domain = next(d["domain"] for d in response.json()["hydra:member"] if d["isActive"] and not d["isPrivate"])
    for index, pair in enumerate(load_vault()[KEY]["pairs"]):
        for role in ["a", "b"]:
            entry = load_vault()[KEY]["pairs"][index][role]
            if entry["status"] == "created" and entry["provider"] == "Mail.tm":
                print(json.dumps({"pair":pair["pair_id"],"role":role,"email":entry["email"],"status":"already_created"}), flush=True)
                continue
            if entry["provider"] != "Mail.tm":
                local = entry["email"].split("@")[0].replace(".", "") + role
                entry["email"] = local + "@" + domain
                entry["provider"] = "Mail.tm"
                entry["status"] = "planned"
                save_entry(index, role, entry)
            try:
                if entry["status"] not in {"created_unverified","created"}:
                    created = session.post("https://api.mail.tm/accounts", json={"address":entry["email"],"password":entry["password"]}, timeout=20)
                    created.raise_for_status()
                    entry["email"] = created.json()["address"]
                    entry["account_id"] = created.json()["id"]
                    entry["status"] = "created_unverified"
                    save_entry(index, role, entry)
                time.sleep(0.35)
                token = session.post("https://api.mail.tm/token", json={"address":entry["email"],"password":entry["password"]}, timeout=20)
                token.raise_for_status()
                entry["mail_token"] = token.json()["token"]
                me = session.get("https://api.mail.tm/me", headers={"Authorization":"Bearer "+entry["mail_token"]}, timeout=20)
                me.raise_for_status()
                identity = me.json()
                if identity["address"] != entry["email"] or identity["isDisabled"] or identity["isDeleted"]:
                    raise RuntimeError("Mailbox authentication returned an unusable identity")
                entry["status"] = "created"
                entry["verified_on"] = "2026-10-09"
                entry["quota_bytes"] = identity.get("quota")
                save_entry(index, role, entry)
                print(json.dumps({"pair":pair["pair_id"],"role":role,"email":entry["email"],"status":"created_and_authenticated"}), flush=True)
                time.sleep(0.35)
            except Exception as exc:
                print(json.dumps({"pair":pair["pair_id"],"role":role,"status":"stopped","error":str(exc)}), flush=True)
                raise
    vault = load_vault()
    vault[KEY]["provider_selection"] = "Persistent receive-only Mail.tm inboxes, user selected"
    for pair in vault[KEY]["pairs"]:
        pair["mutual_recovery"] = "paired_only_provider_has_no_password_reset"
        pair["mega"]["email"] = pair["a"]["email"]
    save_vault(vault)
    export_pairs(vault[KEY])

if __name__ == "__main__":
    main()
