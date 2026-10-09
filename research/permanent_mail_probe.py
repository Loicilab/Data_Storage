"""Read the permanent mailbox signup pages, without submitting."""
import asyncio
import json
from cloud_signup_probe import observe, OUT
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width":1280,"height":960})
        results = await asyncio.gather(*(observe(context, name, url) for name, url in {
            "outlook-mail":"https://signup.live.com/",
            "proton-mail":"https://account.proton.me/signup",
        }.items()))
        (OUT / "permanent-mail-initial.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        for r in results:
            print(json.dumps({k:r.get(k) for k in ["provider","url","title","text","fields","error"]}, indent=2), flush=True)
        await browser.close()

asyncio.run(main())
