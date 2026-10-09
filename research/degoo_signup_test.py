"""Observe and test the normal Degoo signup flow without CAPTCHA solving."""
import asyncio
import sys
from cloud_signup_execute import account, PROFILE, observe, type_secret
from playwright.async_api import async_playwright

async def main(submit, check=False):
    credentials = account("degoo") if submit or check else None
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / "degoo"),channel="chrome",headless=True,viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            if check:
                await page.goto("https://app.degoo.com",wait_until="domcontentloaded")
                await page.wait_for_timeout(20000)
                await observe(page,"degoo","session-check")
                return
            await page.goto("https://app.degoo.com/login",wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.get_by_role("button",name="Sign up",exact=True).click()
            await page.wait_for_timeout(2000)
            await observe(page,"degoo","signup-form")
            if submit:
                await page.locator("input[type=email]:visible").fill(credentials["email"])
                await type_secret(page,page.locator("input[type=password]:visible"),credentials["password"])
                await page.get_by_role("button",name="Create account",exact=True).click()
                await page.wait_for_timeout(5000)
                await observe(page,"degoo","after-submission")
        finally:
            await context.close()

asyncio.run(main("--submit" in sys.argv, "--check" in sys.argv))
