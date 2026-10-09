"""Normal UI signup steps; stops before any interactive CAPTCHA challenge."""
import argparse
import asyncio
import secrets
from cloud_signup_execute import account, PROFILE, observe
from playwright.async_api import async_playwright

async def main(provider):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / provider), channel="chrome", headless=True, viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            if provider == "drime":
                credentials = account(provider, local_part="noravoss" + str(1000 + secrets.randbelow(9000)))
                await page.goto("https://app.drime.cloud/register", wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
                reject = page.get_by_role("button", name="Reject All", exact=True)
                if await reject.count():
                    await reject.click()
                await page.locator("input[type=email]:visible").fill(credentials["email"])
                await page.get_by_role("button", name="Continue", exact=True).click()
                await page.wait_for_timeout(5000)
                await observe(page, provider, "after-email")
            elif provider == "mediafire":
                await page.goto("https://www.mediafire.com/upgrade/", wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                dismiss = page.get_by_text("Dismiss", exact=True)
                if await dismiss.count():
                    await dismiss.click()
                await page.locator("#planFree").click()
                await page.wait_for_timeout(5000)
                await observe(page, provider, "free-signup-form")
        finally:
            await context.close()

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["drime","mediafire"])
asyncio.run(main(parser.parse_args().provider))
