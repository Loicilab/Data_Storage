"""Record the observed Proton suspension, without creating a MEGA account."""
import json
import csv
from cloud_signup_execute import load_vault, save_vault
from permanent_email_pairs import KEY, DEST, pair_csv_rows

def record():
    vault = load_vault()
    batch = vault[KEY]
    with (DEST / "email-pairs.csv").open(encoding="utf-8-sig", newline="") as source:
        saved_rows = {row["pair_id"]: row for row in csv.DictReader(source)}
    for saved_pair in batch["pairs"]:
        saved = saved_rows[saved_pair["pair_id"]]
        for role in ("a", "b"):
            if saved["email_" + role] != saved_pair[role]["email"]:
                raise RuntimeError("Unexpected address change; do not overwrite the user's table")
            if saved["password_" + role] != saved_pair[role]["password"]:
                saved_pair[role]["password"] = saved["password_" + role]
                saved_pair[role]["password_source"] = "user_edited_csv"
    pair = batch["pairs"][0]
    pair["b"]["status"] = "suspended_observed"
    pair["b"]["last_error"] = "Proton sign-in reports: account suspended by automated anti-abuse system."
    pair["b"]["checked_on"] = "2026-10-09"
    pair["mega"]["email"] = pair["b"]["email"]
    pair["mega"]["status"] = "not_created_mailbox_suspended"
    batch["creation_status"] = "proton_created_user_reported_lena_suspended"
    save_vault(vault)
    records = pair_csv_rows(batch)
    manifest = json.loads((DEST / "email-pairs.json").read_text(encoding="utf-8"))
    manifest["pairs"] = [{k:v for k,v in r.items() if not k.startswith("password_")} for r in records]
    manifest["notice"] = "User reports the Proton inboxes created. Lena's sign-in reports a suspension; other inboxes have not been independently checked. Mailfence addresses remain proposals. Pairing does not configure recovery or copy files."
    (DEST / "email-pairs.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return records

if __name__ == "__main__":
    record()
    print("Lena suspension recorded; no MEGA signup submitted.")
