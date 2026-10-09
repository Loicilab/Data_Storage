"""One replacement-provider signup test in an isolated Chrome profile."""
import asyncio
import re
from urllib.parse import urlsplit
import requests
from bs4 import BeautifulSoup
from cloud_signup_execute import account, OUT, PROFILE, observe, type_secret
from playwright.async_api import async_playwright

def activation_link(credentials):
    headers = {"Authorization":"Bearer " + credentials["mail_token"]}
    response = requests.get("https://api.mail.tm/messages",headers=headers,timeout=15)
    response.raise_for_status()
    for item in response.json()["hydra:member"]:
        response = requests.get("https://api.mail.tm/messages/" + item["id"],headers=headers,timeout=15)
        response.raise_for_status()
        message = response.json()
        html = "\n".join(message.get("html") or [])
        links = [a.get("href","") for a in BeautifulSoup(html,"html.parser").select("a[href]")]
        links += re.findall(r"https?://[^\s<>\"']+", message.get("text", ""))
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme == "https" and parsed.hostname == "app.koofr.net" and any(s in parsed.path.lower() for s in ["register", "signup", "confirm", "activate"]):
                return link
    return None

async def main():
    credentials = account("koofr")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / "koofr"),channel="chrome",headless=True,viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            await page.goto("https://app.koofr.net/signup",wait_until="domcontentloaded")
            await page.locator("#email").fill(credentials["email"])
            await page.locator("#consent").check()
            await page.get_by_role("button",name="Create free account",exact=True).click()
            await page.wait_for_timeout(3000)
            await observe(page,"koofr","after-email-submission")
            link = None
            for _ in range(15):
                link = activation_link(credentials)
                if link:
                    break
                await asyncio.sleep(2)
            if not link:
                print("No matching Koofr activation email received within test window",flush=True)
                return
            await page.goto(link,wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            await observe(page,"koofr","activation-form")
            password_fields = page.locator("input[type=password]:visible")
            for index in range(await password_fields.count()):
                await type_secret(page,password_fields.nth(index),credentials["password"])
            if await password_fields.count():
                await observe(page,"koofr","password-form-ready")
                print("Password form ready; inspect button and remaining required fields",flush=True)
        finally:
            await context.close()

asyncio.run(main())
