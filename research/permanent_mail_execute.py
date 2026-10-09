"""One normal signup step for a prepared pair; credentials stay DPAPI protected."""
import argparse
import asyncio
import re
from cloud_signup_execute import load_vault, save_vault, PROFILE, observe, type_secret
from permanent_email_pairs import KEY, export_pairs
from playwright.async_api import async_playwright

async def main(provider, action):
    vault = load_vault()
    pair = vault[KEY]["pairs"][0]
    role = "a" if provider == "outlook" else "b"
    entry = pair[role]
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(PROFILE / (pair["pair_id"]+"-"+provider)), channel="chrome", headless=True, viewport={"width":1280,"height":960})
        page = context.pages[0]
        try:
            if provider == "proton" and action in {"begin","signup"}:
                await page.goto("https://account.proton.me/signup", wait_until="domcontentloaded")
                await page.wait_for_timeout(4000)
                if action == "begin":
                    await observe(page, "permanent-"+provider, "before-free-plan")
                await page.get_by_role("button", name=re.compile(r"^Free\b")).click()
                await page.wait_for_timeout(3000)
                if action == "signup":
                    frame = None
                    for candidate in page.frames:
                        if await candidate.locator("#username:visible").count():
                            frame = candidate
                            break
                    if frame is None:
                        raise RuntimeError("Proton's username input was not available")
                    await frame.locator("#username").fill(entry["email"].split("@")[0])
                    await type_secret(page, page.locator("#password"), entry["password"])
                    await page.wait_for_timeout(600)
                    confirmation = page.locator("#password-confirm:visible")
                    if await confirmation.count():
                        await type_secret(page, confirmation, entry["password"])
                    await page.get_by_role("button", name="Start using Proton Mail now", exact=True).click()
                    await page.wait_for_timeout(5000)
                    vault = load_vault()
                    vault[KEY]["pairs"][0][role]["status"] = "signup_submitted"
                    save_vault(vault)
                    export_pairs(vault[KEY])
            elif provider == "outlook" and action == "begin":
                await page.goto("https://outlook.com/", wait_until="domcontentloaded")
                await page.wait_for_timeout(3500)
            elif provider == "outlook" and action == "signup":
                await page.goto("https://go.microsoft.com/fwlink/p/?linkid=2125440&clcid=0x409&culture=en-us&country=us", wait_until="domcontentloaded")
                await page.wait_for_selector("input:visible", timeout=25000)
                await page.wait_for_timeout(1000)
            elif provider == "outlook" and action == "details":
                await page.goto(entry["flow_url"], wait_until="domcontentloaded")
                await page.get_by_label("New email", exact=True).fill(entry["email"].split("@")[0])
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.wait_for_timeout(2500)
            elif provider == "outlook" and action == "password":
                await page.goto(entry["flow_url"], wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                new_email = page.get_by_label("New email", exact=True)
                if await new_email.count():
                    await new_email.fill(entry["email"].split("@")[0])
                    await page.get_by_role("button", name="Next", exact=True).click()
                await type_secret(page, page.locator("input[type=password]:visible"), entry["password"])
                await page.get_by_role("button", name="Next", exact=True).click()
                await page.wait_for_timeout(2500)
            await observe(page, "permanent-"+provider, action)
            print({"links":await page.get_by_role("link").evaluate_all("els => els.map(e=>({text:e.innerText,url:e.href.split('?')[0].split('#')[0]})).filter(e=>/free|account|sign|create/i.test(e.text))")}, flush=True)
            print({"frame_fields":[{"host":f.url.split('?')[0],"fields":await f.locator('input:visible,button:visible').evaluate_all("els=>els.map(e=>({tag:e.tagName,id:e.id,type:e.type,name:e.name,label:e.getAttribute('aria-label'),text:e.tagName==='BUTTON'?e.innerText:undefined}))")} for f in page.frames if f != page.main_frame]},flush=True)
            vault = load_vault()
            vault[KEY]["pairs"][0][role]["flow_url"] = page.url
            save_vault(vault)
            export_pairs(vault[KEY])
        finally:
            await context.close()

parser = argparse.ArgumentParser()
parser.add_argument("provider", choices=["outlook","proton"])
parser.add_argument("action", choices=["begin","observe","signup","details","password"])
args = parser.parse_args()
asyncio.run(main(args.provider, args.action))
