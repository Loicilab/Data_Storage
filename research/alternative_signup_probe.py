"""Read candidate signup forms without submitting or changing user profiles."""
import asyncio
import json
from cloud_signup_probe import observe, OUT
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width":1280,"height":960})
        results = await asyncio.gather(*(
            observe(context, name, url) for name,url in {
                "drime": "https://app.drime.cloud/register",
            }.items()
        ))
        (OUT / "drime-signup-observations.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
        print(json.dumps(results,indent=2))
        await browser.close()

asyncio.run(main())
