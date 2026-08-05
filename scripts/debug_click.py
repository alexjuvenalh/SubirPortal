"""Debug: check browser console and try real user interaction."""
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

        # Capture console messages
        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        print("=== JS Console (carga inicial) ===")
        for m in console_msgs[-20:]:
            print(m)
        console_msgs.clear()

        # Try real user-like interaction: click the select, then click the option
        print("\n=== Probando interaccion real (click) ===")
        sel = page.locator("#edit-field-tipo-de-norma-shs-0-0")
        await sel.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)
        await sel.click()
        await asyncio.sleep(1)
        
        # Click option 115
        option = page.locator("#edit-field-tipo-de-norma-shs-0-0 option[value='115']")
        await option.click()
        await asyncio.sleep(8)

        print("\n=== JS Console (despues de click) ===")
        for m in console_msgs:
            print(m)

        # Check level 2
        html_l2 = await page.evaluate("""
            () => {
                const container = document.querySelector(
                    '#edit-field-tipo-de-norma-wrapper [data-shs-level="1"]'
                );
                return container ? container.innerHTML.substring(0, 500) : 'NOT FOUND';
            }
        """)
        print(f"\nContenido nivel 2: {html_l2}")

        # Also check for any select with shs in id    
        selects = await page.evaluate("""
            () => Array.from(document.querySelectorAll('select[id*="shs"]'))
                .map(s => s.id)
        """)
        print(f"\nTodos los selects shs: {selects}")

        await asyncio.sleep(2)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
