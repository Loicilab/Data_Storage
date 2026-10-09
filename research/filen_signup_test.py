"""Normal Filen signup in an isolated profile; secrets retained with Windows DPAPI."""
import asyncio
import sys
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
from cloud_signup_execute import account, PROFILE, OUT, observe, type_secret, load_vault, save_vault
from playwright.async_api import async_playwright

def activation_link(credentials):
    headers = {"Authorization": "Bearer " + credentials["mail_token"]}
    response = requests.get("https://api.mail.tm/messages", headers=headers, timeout=15)
    response.raise_for_status()
    for item in response.json()["hydra:member"]:
        response = requests.get("https://api.mail.tm/messages/" + item["id"], headers=headers, timeout=15)
        response.raise_for_status()
        message = response.json()
        html = "\n".join(message.get("html") or [])
        for anchor in BeautifulSoup(html, "html.parser").select("a[href]"):
            link = anchor.get("href", "")
            parsed = urlsplit(link)
            if parsed.scheme == "https" and parsed.hostname in {"filen.io", "app.filen.io", "drive.filen.io", "filen.net"} and any(s in (parsed.path + parsed.fragment).lower() for s in ["confirm", "activate", "verify"]):
                return link
    return None

async def main(action):
    credentials = account("filen")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / "filen"), channel="chrome", headless=True, viewport={"width": 1280,"height":960})
        page = context.pages[0]
        try:
            if action == "signup":
                await page.goto("https://app.filen.io/#/register",wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                if await page.get_by_role("button",name="Only needed",exact=True).count():
                    await page.get_by_role("button",name="Only needed",exact=True).click()
                await observe(page,"filen","before-signup")
                await page.locator("#email").fill(credentials["email"])
                await type_secret(page,page.locator("#password"),credentials["password"])
                await type_secret(page,page.locator("#confirmPassword"),credentials["password"])
                await page.get_by_role("button",name="Create account",exact=True).click()
                await page.wait_for_timeout(6000)
                await observe(page,"filen","after-submission")
            elif action == "activate":
                link = None
                for _ in range(15):
                    link = activation_link(credentials)
                    if link:
                        break
                    await asyncio.sleep(2)
                if not link:
                    print("No matching Filen activation link received",flush=True)
                    return
                await page.goto(link,wait_until="domcontentloaded")
                await page.wait_for_timeout(6000)
                await observe(page,"filen","after-activation")
            else:
                await page.goto("https://app.filen.io/#/login",wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                await observe(page,"filen","before-login")
                if await page.locator("#email").count():
                    await page.locator("#email").fill(credentials["email"])
                    await type_secret(page,page.locator("#password"),credentials["password"])
                    await page.get_by_role("button",name="Login",exact=True).click()
                    await page.wait_for_timeout(7000)
                await observe(page,"filen","after-login")
        finally:
            await context.close()

asyncio.run(main(sys.argv[1] if len(sys.argv)>1 else "signup"))
