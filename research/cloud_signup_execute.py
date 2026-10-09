"""One isolated test account per selected provider, with DPAPI protected secrets."""
import argparse
import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools")
from playwright.async_api import async_playwright

OUT = Path(__file__).parent / "signup-evidence"
VAULT = Path(__file__).parent / "test-credentials.dpapi"
PROFILE = Path(r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-profiles")

class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

def dpapi(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    library = ctypes.windll.crypt32
    fn = library.CryptUnprotectData if decrypt else library.CryptProtectData
    description = None if decrypt else "Cloud signup test credentials"
    success = fn(ctypes.byref(incoming), description, None, None, None, 1, ctypes.byref(outgoing))
    if not success:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)

def load_vault():
    return json.loads(dpapi(VAULT.read_bytes(), True)) if VAULT.exists() else {}

def save_vault(data):
    VAULT.write_bytes(dpapi(json.dumps(data).encode()))

async def type_secret(page, field, secret):
    for _ in range(2):
        await field.fill("")
        await field.click()
        await page.wait_for_timeout(500)
        await field.press_sequentially(secret, delay=100)
        await page.wait_for_timeout(300)
        if await field.input_value() == secret:
            return
    raise RuntimeError("Browser did not preserve typed password; registration not submitted")

def account(provider, local_part=None):
    data = load_vault()
    if provider in data:
        return data[provider]
    session = requests.Session()
    domains = session.get("https://api.mail.tm/domains", timeout=20).json()["hydra:member"]
    domain = next(d["domain"] for d in domains if d["isActive"] and not d["isPrivate"])
    email = f"{local_part or ('cloudtest' + secrets.token_hex(7))}@{domain}"
    mailbox_password = "Mailbox!" + secrets.token_urlsafe(24)
    response = session.post("https://api.mail.tm/accounts", json={"address": email, "password": mailbox_password}, timeout=20)
    response.raise_for_status()
    email = response.json().get("address", email)
    token = session.post("https://api.mail.tm/token", json={"address": email, "password": mailbox_password}, timeout=20)
    token.raise_for_status()
    data[provider] = {"email": email, "password": "Cloud!7" + secrets.token_urlsafe(24), "mail_password": mailbox_password, "mail_token": token.json()["token"], "username": "cloudtest" + secrets.token_hex(5)}
    save_vault(data)
    return data[provider]

def confirmation_link(credentials, provider):
    headers = {"Authorization": "Bearer " + credentials["mail_token"]}
    messages = requests.get("https://api.mail.tm/messages", headers=headers, timeout=15)
    messages.raise_for_status()
    for item in messages.json()["hydra:member"]:
        message = requests.get("https://api.mail.tm/messages/" + item["id"], headers=headers, timeout=15)
        message.raise_for_status()
        content = message.json()
        html = "\n".join(content.get("html") or [])
        links = [a.get("href", "") for a in BeautifulSoup(html, "html.parser").select("a[href]")]
        links += re.findall(r"https?://[^\s<>\"']+", content.get("text", ""))
        for link in links:
            parsed = urlsplit(link)
            if provider == "mega" and parsed.hostname in {"mega.nz", "mega.io", "www.mega.nz", "www.mega.io"} and "confirm" in (parsed.path + parsed.fragment):
                return link
            if provider == "blomp" and parsed.hostname == "dashboard.blomp.com" and any(word in parsed.path for word in ["verify", "activate", "confirm"]):
                return link
    return None

def google_email_code(credentials):
    headers = {"Authorization": "Bearer " + credentials["mail_token"]}
    response = requests.get("https://api.mail.tm/messages", headers=headers, timeout=15)
    response.raise_for_status()
    for item in response.json()["hydra:member"]:
        sender = item.get("from", {}).get("address", "")
        if sender.rsplit("@", 1)[-1] not in {"google.com", "accounts.google.com"}:
            continue
        message = requests.get("https://api.mail.tm/messages/" + item["id"], headers=headers, timeout=15)
        message.raise_for_status()
        text = message.json().get("text", "")
        match = re.search(r"\b\d{6}\b", text)
        if match:
            return match.group()
    return None

async def observe(page, provider, stage):
    parsed_url = urlsplit(page.url)
    safe_path = re.sub(r"/(activate|verify|confirm)/[^/]+", r"/\1/[REDACTED]", parsed_url.path)
    safe_path = re.sub(r"/confirm[^/]*", "/confirm[REDACTED]", safe_path)
    result = {
        "provider": provider, "stage": stage,
        "url_path": parsed_url.scheme + "://" + parsed_url.netloc + safe_path,
        "title": re.sub(r"https?://\S+", "[FLOW URL]", await page.title()),
        "text": (await page.locator("body").inner_text())[:10000],
        "fields": await page.locator("input:visible,select:visible,button:visible").evaluate_all(
            "els => els.map(e => ({tag:e.tagName,type:e.type,name:e.name,id:e.id,placeholder:e.placeholder,label:e.getAttribute('aria-label'),text:e.tagName==='BUTTON'?e.innerText:undefined}))"
        ),
        "frames": [urlsplit(f.url).netloc + re.sub(r"/(activate|verify|confirm)/[^/]+", r"/\1/[REDACTED]", re.sub(r"/confirm[^/]*", "/confirm[REDACTED]", urlsplit(f.url).path)) for f in page.frames],
    }
    (OUT / f"{provider}-{stage}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if provider == "google":
        data = load_vault()
        if provider in data:
            data[provider]["flow_url"] = page.url
            save_vault(data)
    await page.screenshot(path=str(OUT / f"{provider}-{stage}.png"), full_page=True)
    print(json.dumps(result, indent=2), flush=True)

async def run(provider, action):
    OUT.mkdir(parents=True, exist_ok=True)
    credentials = None
    if provider != "google" or action in {"email", "verify", "password", "finish", "complete"}:
        credentials = account(provider)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / provider), channel="chrome", headless=True, viewport={"width": 1280, "height": 960})
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            if provider == "mega":
                if action in {"signup", "complete"}:
                    await page.goto("https://mega.nz/register", wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)
                    await page.locator("#register-firstname").fill("Cloud Test")
                    await page.locator("#register-email").fill(credentials["email"])
                    await type_secret(page, page.locator("#register-password"), credentials["password"])
                    await page.locator("#register-firstname").click()
                    print(json.dumps({"provider":provider,"field_lengths":await page.locator("input:visible").evaluate_all("els => els.map(e=>({id:e.id,length:e.value.length}))")}), flush=True)
                    await page.get_by_role("button", name="Sign up", exact=True).click()
                    await page.wait_for_timeout(6000)
                    await observe(page, provider, "submitted")
                    if action == "complete":
                        for _ in range(15):
                            link = confirmation_link(credentials, provider)
                            if link:
                                break
                            await asyncio.sleep(2)
                        if not link:
                            print("No activation email received within the test window", flush=True)
                            return
                        await page.goto(link, wait_until="domcontentloaded")
                        await page.wait_for_timeout(5000)
                        await observe(page, provider, "first-activation-visit")
                        if "Confirm your account" in await page.locator("body").inner_text():
                            await type_secret(page, page.locator("input[type=password]:visible").first, credentials["password"])
                            await page.get_by_role("button", name="Confirm", exact=True).click()
                            await page.wait_for_timeout(7000)
                        await observe(page, provider, "activated")
                    return
                if action in {"confirm", "activate"}:
                    link = confirmation_link(credentials, provider)
                    if not link:
                        print(json.dumps({"provider":provider,"stage":"confirm","result":"No confirmation email received yet"}), flush=True)
                        return
                    await page.goto(link, wait_until="domcontentloaded")
                    await page.wait_for_timeout(5000)
                    if action == "activate":
                        await observe(page, provider, "before-activation")
                        if "Confirm your account" in await page.locator("body").inner_text():
                            await page.locator("input[type=password]:visible").first.press_sequentially(credentials["password"], delay=25)
                            await page.get_by_role("button", name="Confirm", exact=True).click()
                            await page.wait_for_timeout(7000)
                    await observe(page, provider, "activated" if action == "activate" else "confirmation-opened")
                    return
                if action == "login":
                    await page.goto("https://mega.nz/login", wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)
                    await page.locator("input[type=text]:visible").first.fill(credentials["email"])
                    await type_secret(page, page.locator("input[type=password]:visible").first, credentials["password"])
                    await page.get_by_role("button", name=re.compile(r"^Log\s*in$", re.I)).click()
                    await page.wait_for_timeout(7000)
                    await observe(page, provider, "logged-in")
                    return
                await page.goto("https://mega.nz/fm", wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)
                await observe(page, provider, action)
            elif provider == "blomp":
                if action == "activate":
                    link = None
                    for _ in range(15):
                        link = confirmation_link(credentials, provider)
                        if link:
                            break
                        await asyncio.sleep(2)
                    if not link:
                        print("No Blomp activation email received within the test window", flush=True)
                        return
                    parsed_link = urlsplit(link)
                    if parsed_link.scheme != "https":
                        link = parsed_link._replace(scheme="https").geturl()
                    await page.goto(link, wait_until="domcontentloaded")
                    await page.wait_for_timeout(4000)
                    await observe(page, provider, "activated")
                    return
                await page.goto("https://dashboard.blomp.com/register", wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                if action in {"signup", "captcha", "captcha-live"}:
                    await page.locator("input[name=name]").fill("Cloud Integration Test")
                    await page.locator("input[name=email]").fill(credentials["email"])
                    await page.locator("input[name=password]").fill(credentials["password"])
                    await page.locator("input[name=password_confirmation]").fill(credentials["password"])
                    await page.locator("input[name=forum_username]").fill(credentials["username"])
                    await page.locator("label[for=agree]").click(position={"x":5,"y":10})
                    await observe(page, provider, "ready-for-captcha")
                    if action in {"captcha", "captcha-live"}:
                        anchor = next(f for f in page.frames if "/recaptcha/api2/anchor" in f.url)
                        print(json.dumps({"provider":"blomp","captcha_frame_text":await anchor.locator("body").inner_text()}), flush=True)
                        await anchor.get_by_role("checkbox").click()
                        await page.wait_for_timeout(9000)
                        await observe(page, provider, "after-captcha-checkbox")
                        response_box = page.locator("textarea[name=g-recaptcha-response]")
                        if action == "captcha-live":
                            for turn in range(24):
                                if await response_box.count() and await response_box.input_value():
                                    print("CAPTCHA accepted", flush=True)
                                    break
                                challenge = next(f for f in page.frames if "/recaptcha/api2/bframe" in f.url)
                                tiles = challenge.locator("td")
                                screenshot = OUT / "blomp-current-captcha.png"
                                await page.screenshot(path=str(screenshot), full_page=True)
                                print(json.dumps({"captcha_turn":turn,"text":(await challenge.locator("body").inner_text())[:2000],"tile_count":await tiles.count(),"screenshot":str(screenshot)}), flush=True)
                                command_path = OUT / "blomp-captcha-command.json"
                                while not command_path.exists():
                                    await asyncio.sleep(0.25)
                                command = json.loads(command_path.read_text(encoding="utf-8-sig"))
                                command_path.unlink()
                                if command.get("stop"):
                                    break
                                for tile in command.get("tiles", []):
                                    await tiles.nth(tile).click()
                                if command.get("verify"):
                                    await challenge.get_by_role("button", name=re.compile(r"^(VERIFY|NEXT)$", re.I)).click()
                                if command.get("click"):
                                    await page.mouse.click(command["click"][0], command["click"][1])
                                await page.wait_for_timeout(8000)
                        for frame in page.frames:
                            if "/recaptcha/api2/bframe" in frame.url:
                                print(json.dumps({"provider":"blomp","captcha_challenge_text":(await frame.locator("body").inner_text())[:2000]}), flush=True)
                        if await response_box.count() and await response_box.input_value():
                            await page.get_by_role("button", name=re.compile(r"^Register$", re.I)).click()
                            await page.wait_for_timeout(5000)
                            await observe(page, provider, "submitted")
            else:
                if action in {"verify", "password", "finish"}:
                    await page.goto(credentials["flow_url"], wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)
                    if action == "verify":
                        code = google_email_code(credentials)
                        if not code:
                            print("No Google email code received yet", flush=True)
                            return
                        await page.locator("#code").fill(code)
                        await page.get_by_role("button", name="Next", exact=True).click()
                        await page.wait_for_timeout(3000)
                        await observe(page, provider, "after-verification")
                    elif action == "password":
                        fields = page.locator("input[type=password]:visible")
                        if await fields.count() != 2:
                            await observe(page, provider, "unexpected-password-stage")
                            return
                        await type_secret(page, fields.nth(0), credentials["password"])
                        await type_secret(page, fields.nth(1), credentials["password"])
                        await page.get_by_role("button", name="Next", exact=True).click()
                        await page.wait_for_timeout(4000)
                        await observe(page, provider, "after-password")
                    else:
                        await observe(page, provider, "next-stage")
                    return
                await page.goto("https://accounts.google.com/signup", wait_until="domcontentloaded")
                await page.locator("#firstName").fill("Cloud Integration Test")
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.wait_for_timeout(2500)
                await observe(page, provider, "after-name")
                if action in {"birthday", "email", "complete"}:
                    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
                    month = secrets.choice(months)
                    gender = secrets.choice(["Female", "Male"])
                    await page.get_by_role("combobox").filter(has_text=re.compile(r"^Month$")).click()
                    await page.get_by_role("option", name=month, exact=True).click()
                    await page.locator("#day").fill(str(1+secrets.randbelow(28)))
                    await page.locator("#year").fill(str(1970+secrets.randbelow(31)))
                    await page.get_by_role("combobox").filter(has_text=re.compile(r"^Gender$")).click()
                    await page.get_by_role("option", name=gender, exact=True).click()
                    await page.get_by_role("button", name="Next", exact=True).click()
                    await page.wait_for_timeout(3000)
                    await observe(page, provider, "after-birthday")
                    if action in {"email", "complete"}:
                        await page.get_by_role("button", name="Use your existing email", exact=True).click()
                        await page.wait_for_timeout(1000)
                        await observe(page, provider, "existing-email-form")
                        email_input = page.locator("input[type=email]:visible")
                        if await email_input.count() != 1:
                            return
                        await email_input.fill(credentials["email"])
                        await page.get_by_role("button", name="Next", exact=True).click()
                        await page.wait_for_timeout(4000)
                        await observe(page, provider, "after-email")
                        if action == "complete" and await page.locator("#code").count():
                            code = None
                            for _ in range(10):
                                code = google_email_code(credentials)
                                if code:
                                    break
                                await asyncio.sleep(2)
                            if not code:
                                print("No Google verification code received", flush=True)
                                return
                            await page.locator("#code").fill(code)
                            await page.get_by_role("button", name="Next", exact=True).click()
                            await page.wait_for_timeout(2500)
                            await observe(page, provider, "after-verification")
                            fields = page.locator("input[type=password]:visible")
                            if await fields.count() == 2:
                                await type_secret(page, fields.nth(0), credentials["password"])
                                await type_secret(page, fields.nth(1), credentials["password"])
                                await page.get_by_role("button", name="Next", exact=True).click()
                                await page.wait_for_timeout(3500)
                                await observe(page, provider, "after-password")
        finally:
            await context.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=["mega", "blomp", "google"])
    parser.add_argument("action", choices=["signup", "confirm", "activate", "observe", "login", "birthday", "email", "complete", "verify", "password", "finish", "captcha", "captcha-live"])
    args = parser.parse_args()
    asyncio.run(run(args.provider, args.action))
