"""Debug: monitor network requests when selecting SHS option."""
import asyncio
import io
import sys
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

        # Monitor ALL network requests
        requests = []
        def on_request(req):
            if "shs" in req.url.lower() or "ajax" in req.url.lower() or "taxonomy" in req.url.lower():
                requests.append(f"REQ: {req.method} {req.url}")
        def on_response(resp):
            if "shs" in resp.url.lower() or "ajax" in resp.url.lower() or "taxonomy" in resp.url.lower():
                requests.append(f"RESP [{resp.status}] {resp.url}")

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        print("Requests during page load:")
        for r in requests:
            print(f"  {r}")
        requests.clear()

        print("\n--- Selecting nivel 1 (value='115') ---")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")
        await asyncio.sleep(8)

        print(f"\nRequests after select ({len(requests)}):")
        for r in requests:
            print(f"  {r}")

        if not requests:
            print("  NO AJAX/SHS requests detected!")

        # Try manual jQuery trigger
        print("\n--- Trying jQuery trigger ---")
        requests.clear()
        result = await page.evaluate("""
            () => {
                const sel = document.getElementById('edit-field-tipo-de-norma-shs-0-0');
                sel.value = '115';
                if (typeof jQuery !== 'undefined') {
                    jQuery(sel).trigger('change');
                    return 'jQuery change triggered';
                }
                return 'jQuery not available';
            }
        """)
        print(f"Result: {result}")
        await asyncio.sleep(5)
        print(f"Requests after jQuery trigger ({len(requests)}):")
        for r in requests:
            print(f"  {r}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
