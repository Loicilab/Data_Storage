"""Create one MEGA account using the first actually registered mailbox pair."""
import asyncio
import re
from cloud_signup_execute import load_vault, save_vault, PROFILE, observe, type_secret, confirmation_link
from permanent_email_pairs import KEY, export_pairs
from playwright.async_api import async_playwright

async def main():
    vault = load_vault()
    pair = vault[KEY]["pairs"][0]
    if pair["a"]["status"] != "created" or pair["a"]["provider"] != "Mail.tm":
        raise RuntimeError("The selected inbox must be created and authenticated before MEGA registration")
    if pair["mega"]["status"] != "not_created":
        raise RuntimeError("A signup was already attempted for this pair; inspect evidence instead of registering again")
    credentials = {"email":pair["a"]["email"],"password":pair["mega"]["password"],"mail_token":pair["a"]["mail_token"]}
    vault["mega_pair_01"] = credentials
    save_vault(vault)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / "mega-pair-01"), channel="chrome", headless=True, viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            await page.goto("https://mega.nz/register", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            await page.locator("#register-firstname").fill(pair["name"])
            await page.locator("#register-email").fill(credentials["email"])
            await type_secret(page, page.locator("#register-password"), credentials["password"])
            await page.locator("#register-firstname").click()
            await page.get_by_role("button", name="Sign up", exact=True).click()
            vault = load_vault()
            vault[KEY]["pairs"][0]["mega"]["status"] = "signup_submitted"
            save_vault(vault)
            export_pairs(vault[KEY])
            await page.wait_for_timeout(6000)
            await observe(page, "mega-pair-01", "submitted")
            link = None
            for _ in range(15):
                link = confirmation_link(credentials, "mega")
                if link:
                    break
                await asyncio.sleep(2)
            if not link:
                print("No MEGA confirmation email received within test window", flush=True)
                return
            await page.goto(link, wait_until="domcontentloaded")
            await page.wait_for_timeout(4500)
            if "Confirm your account" in await page.locator("body").inner_text():
                await type_secret(page, page.locator("input[type=password]:visible").first, credentials["password"])
                await page.get_by_role("button", name="Confirm", exact=True).click()
                await page.wait_for_timeout(7000)
            await observe(page, "mega-pair-01", "after-confirmation")
            vault = load_vault()
            vault["mega_pair_01"]["flow_url"] = page.url
            save_vault(vault)
        finally:
            await context.close()

asyncio.run(main())
