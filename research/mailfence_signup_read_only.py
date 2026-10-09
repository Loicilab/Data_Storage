"""Read the alternative email signup form without registering an account."""
import asyncio
import json
from cloud_signup_execute import OUT
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page()
        await page.goto("https://mailfence.com/registration/?lg=en", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        result = {"checked_on":"2026-10-09", "url":page.url.split("?")[0],
                  "text":(await page.locator("body").inner_text())[:5500],
                  "fields":await page.locator("input:visible,button:visible").evaluate_all("els=>els.map(e=>({tag:e.tagName,type:e.type,name:e.name,id:e.id,maxlength:e.maxLength,placeholder:e.placeholder,text:e.tagName==='BUTTON'?e.innerText:undefined}))")}
        (OUT / "mailfence-signup-read-only.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        await browser.close()

asyncio.run(main())
