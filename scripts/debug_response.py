"""Debug: capture SHS AJAX response body."""
import asyncio
import io
import sys
import json
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            locale="es-PE",
        )
        page = await context.new_page()

        # Capture SHS response bodies
        shs_responses = []
        async def on_response(resp):
            if "/shs-term-data/shs-field-tipo-de-norma" in resp.url:
                try:
                    body = await resp.text()
                    shs_responses.append({"url": resp.url, "status": resp.status, "body": body[:2000]})
                except:
                    shs_responses.append({"url": resp.url, "status": resp.status, "body": "COULD NOT READ"})

        page.on("response", on_response)

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        # Wait for initial SHS data load
        await asyncio.sleep(3)
        
        print("=== Initial SHS responses ===")
        for r in shs_responses:
            print(f"\nURL: {r['url']}")
            print(f"Status: {r['status']}")
            print(f"Body (first 500 chars): {r['body'][:500]}")
        
        shs_responses.clear()

        # Now select nivel 1
        print("\n=== Selecting nivel 1: 115 ===")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")
        await asyncio.sleep(5)

        print("\n=== After select responses ===")
        for r in shs_responses:
            print(f"\nURL: {r['url']}")
            print(f"Status: {r['status']}")
            print(f"Body: {r['body'][:1000]}")

        if not shs_responses:
            print("NO SHS RESPONSES after select!")

        # Check level 2 container
        l2 = await page.evaluate("""
            () => {
                const c = document.querySelector('[data-shs-level="1"]');
                return c ? c.innerHTML.substring(0, 500) : 'NOT FOUND';
            }
        """)
        print(f"\nLevel 2 container after select: {l2}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
