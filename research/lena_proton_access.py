"""Sign in to the user-created Lena mailbox using its saved credential."""
import asyncio
from cloud_signup_execute import PROFILE, observe, load_vault, save_vault, type_secret
from permanent_email_pairs import KEY
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / "lena-proton-mega"), channel="chrome", headless=True, viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            await page.goto("https://mail.proton.me/", wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)
            if await page.locator("#username:visible").count():
                pair = load_vault()[KEY]["pairs"][0]
                await page.locator("#username").fill(pair["b"]["email"])
                await type_secret(page, page.locator("#password"), pair["b"]["password"])
                await page.get_by_role("button", name="Sign in", exact=True).click()
                await page.wait_for_timeout(10000)
            await observe(page, "lena-proton", "login-result")
            if page.url.startswith("https://mail.proton.me/") and not await page.locator("#username:visible").count():
                vault = load_vault()
                vault[KEY]["pairs"][0]["b"]["status"] = "created_verified"
                save_vault(vault)
        finally:
            await context.close()

asyncio.run(main())
