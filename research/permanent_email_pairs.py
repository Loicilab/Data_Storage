"""Prepare and persist ten permanent-mail pairs; never claim unregistered addresses."""
import csv
import json
import secrets
from pathlib import Path
from cloud_signup_execute import load_vault, save_vault

DEST = Path(__file__).parents[1] / "accounts"
KEY = "permanent_mail_pairs"

def pair_csv_rows(batch):
    rows = []
    for pair in batch["pairs"]:
        row = {"pair_id":pair["pair_id"], "generated_name":pair["name"]}
        for role in ("a", "b"):
            row["email_"+role] = pair[role]["email"]
            if batch.get("include_passwords_in_csv", False):
                row["password_"+role] = pair[role]["password"]
            row["provider_"+role] = pair[role]["provider"]
            row["status_"+role] = pair[role]["status"]
        row["mutual_recovery"] = pair["mutual_recovery"]
        row["mega_status"] = pair["mega"]["status"]
        rows.append(row)
    return rows

def export_pairs(batch):
    DEST.mkdir(exist_ok=True)
    rows = []
    for pair in batch["pairs"]:
        rows.append({"pair_id":pair["pair_id"], "generated_name":pair["name"],
                     "email_a":pair["a"]["email"], "provider_a":pair["a"]["provider"], "status_a":pair["a"]["status"],
                     "email_b":pair["b"]["email"], "provider_b":pair["b"]["provider"], "status_b":pair["b"]["status"],
                     "mutual_recovery":pair["mutual_recovery"], "mega_status":pair["mega"]["status"]})
    manifest = {"prepared_on":"2026-10-09", "purpose":"Two permanent inboxes per generated test name; pairs are intended backup partners.",
                "notice":"Addresses with status planned or signup_blocked are not confirmed usable inboxes. Pairing does not configure recovery or copy files.", "pairs":rows}
    (DEST / "email-pairs.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    csv_rows = pair_csv_rows(batch)
    with (DEST / "email-pairs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    return rows

def prepare():
    vault = load_vault()
    if KEY not in vault:
        first_names = ["Nora","Mara","Clara","Lena","Eva","Mira","Sofia","Julia","Lea","Emma","Anna","Nina","Elisa","Lara","Noah","Luca","Elias","Jonas","Felix","Simon","Leon","Milan","David","Adrian","Julian","Theo","Finn","Robin","Armin","Oscar"]
        last_names = ["Voss","Keller","Feld","Baumann","Weber","Steiner","Hartmann","Fischer","Berger","Bauer","Vogel","Seidel","Frank","Sommer","Winter","Brandt","Schulz","Lindner","Wolf","Becker","Hoffmann","Wagner","Kraus","Schuster"]
        random = secrets.SystemRandom()
        pairs = []
        for i, first in enumerate(random.sample(first_names, 10), start=1):
            last = random.choice(last_names)
            local = f"{first.lower()}.{last.lower()}.{1000+secrets.randbelow(9000)}"
            pairs.append({"pair_id":f"pair-{i:02d}", "name":first+" "+last, "first_name":first, "last_name":last,
                          "birthday":{"month":1+secrets.randbelow(12),"day":1+secrets.randbelow(28),"year":1970+secrets.randbelow(31)},
                          "a":{"provider":"Outlook","email":local+"@outlook.com","password":"Mail!7"+secrets.token_urlsafe(24),"status":"planned"},
                          "b":{"provider":"Proton","email":local+"@proton.me","password":"Mail!7"+secrets.token_urlsafe(24),"status":"planned"},
                          "mutual_recovery":"not_configured", "mega":{"email":local+"@outlook.com","password":"Mega!7"+secrets.token_urlsafe(24),"status":"not_created"}})
        vault[KEY] = {"prepared_on":"2026-10-09","pairs":pairs}
        save_vault(vault)
    return export_pairs(vault[KEY])

if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
