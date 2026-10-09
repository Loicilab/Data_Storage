"""Observe cloud signup routes in an isolated browser; never uses a user profile."""
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, r"C:\Users\loici\AppData\Local\Temp\cloud-signup-test-tools")
from playwright.async_api import async_playwright

OUT = Path(__file__).parent / "signup-evidence"
ROUTES = {
    "mega": "https://mega.nz/register",
    "blomp": "https://dashboard.blomp.com/register",
    "google": "https://accounts.google.com/signup",
}

async def observe(context, name, url):
    page = await context.new_page()
    result = {"provider": name, "requested_url": url}
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6000)
        result.update({
            "url": page.url,
            "status": response.status if response else None,
            "title": await page.title(),
            "text": (await page.locator("body").inner_text())[:14000],
            "fields": await page.locator("input:visible,select:visible,button:visible").evaluate_all(
                "els => els.map(e => ({tag:e.tagName,type:e.type,name:e.name,id:e.id,placeholder:e.placeholder,label:e.getAttribute('aria-label'),text:e.tagName==='BUTTON'?e.innerText:undefined}))"
            ),
            "frames": [f.url for f in page.frames],
        })
        await page.screenshot(path=str(OUT / f"{name}-signup.png"), full_page=True)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        await page.close()
    return result

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 960})
        results = await asyncio.gather(*(observe(context, name, url) for name, url in ROUTES.items()))
        (OUT / "initial-signup-observations.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2), flush=True)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
