"""One user-requested Google retry with a fictional person-style test identity."""
import asyncio
import re
import secrets
from cloud_signup_execute import account, PROFILE, observe, type_secret, google_email_code, load_vault, save_vault
from playwright.async_api import async_playwright

PROVIDER = "google-natural-name-3"
VAULT_KEY = "google_human_name"

async def main():
    credentials = account(VAULT_KEY, local_part="marafeld" + str(1000 + secrets.randbelow(9000)))
    details = {"first_name":"Mara", "last_name":"Feld",
               "month":secrets.choice(["January","February","March","April","May","June","July","August","September","October","November","December"]),
               "day":1+secrets.randbelow(28), "year":1970+secrets.randbelow(31),
               "gender":secrets.choice(["Female","Male"])}
    data = load_vault()
    data[VAULT_KEY]["test_details"] = details
    save_vault(data)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / PROVIDER), channel="chrome", headless=True, viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            await page.goto("https://accounts.google.com/signup", wait_until="domcontentloaded")
            await page.locator("#firstName").fill(details["first_name"])
            if await page.locator("#lastName").count():
                await page.locator("#lastName").fill(details["last_name"])
            await page.get_by_role("button", name="Next", exact=True).click()
            await page.wait_for_timeout(2000)
            await observe(page, PROVIDER, "after-name")
            await page.get_by_role("combobox").filter(has_text=re.compile(r"^Month$")).click()
            await page.get_by_role("option", name=details["month"], exact=True).click()
            await page.locator("#day").fill(str(details["day"]))
            await page.locator("#year").fill(str(details["year"]))
            await page.get_by_role("combobox").filter(has_text=re.compile(r"^Gender$")).click()
            await page.get_by_role("option", name=details["gender"], exact=True).click()
            await page.get_by_role("button", name="Next", exact=True).click()
            await page.wait_for_timeout(2500)
            await observe(page, PROVIDER, "after-birthday")
            await page.get_by_role("button", name="Use your existing email", exact=True).click()
            await page.locator("input[type=email]:visible").fill(credentials["email"])
            await page.get_by_role("button", name="Next", exact=True).click()
            await page.wait_for_timeout(3000)
            await observe(page, PROVIDER, "after-email")
            if not await page.locator("#code").count():
                return
            code = None
            for _ in range(15):
                code = google_email_code(credentials)
                if code:
                    break
                await asyncio.sleep(2)
            if not code:
                print("No verification code received within test window", flush=True)
                return
            await page.locator("#code").fill(code)
            await page.get_by_role("button", name="Next", exact=True).click()
            await page.wait_for_timeout(2500)
            await observe(page, PROVIDER, "after-verification")
            fields = page.locator("input[type=password]:visible")
            if await fields.count() != 2:
                return
            await type_secret(page, fields.nth(0), credentials["password"])
            await type_secret(page, fields.nth(1), credentials["password"])
            await page.get_by_role("button", name="Next", exact=True).click()
            await page.wait_for_timeout(4000)
            await observe(page, PROVIDER, "after-password")
            data = load_vault()
            data[VAULT_KEY]["flow_url"] = page.url
            save_vault(data)
        finally:
            await context.close()

asyncio.run(main())
