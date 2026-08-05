"""Debug: keyboard interaction + test alternative SHS options."""
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

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        print("=== Keyboard interaction con select ===")
        sel = page.locator("#edit-field-tipo-de-norma-shs-0-0")
        await sel.scroll_into_view_if_needed()
        await sel.focus()
        await asyncio.sleep(0.5)
        
        # Open dropdown
        await page.keyboard.press(" ")
        await asyncio.sleep(1)
        
        # Arrow down to "Resoluciones Emitidas por la ANA" (it's the 4th option after PEI, RS, RM)
        # PEI is first, so press down 3 times
        for _ in range(3):
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(0.2)
        
        # Select it
        await page.keyboard.press("Enter")
        await asyncio.sleep(5)

        # Check level 2
        html_l2 = await page.evaluate("""
            () => {
                const containers = document.querySelectorAll(
                    '#edit-field-tipo-de-norma-wrapper [data-shs-level]'
                );
                let result = [];
                containers.forEach((c, i) => {
                    result.push(`Level ${c.dataset.shsLevel}: ${c.innerHTML.substring(0, 300)}`);
                });
                return result.join('\\n---\\n');
            }
        """)
        print(f"\nContenido de levels:\n{html_l2}")

        # Check for network activity
        print("\n=== Also trying to test with PGRH option (257217) ===")
        # First reload
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "257217")
        await asyncio.sleep(5)
        html_l2b = await page.evaluate("""
            () => {
                const containers = document.querySelectorAll(
                    '#edit-field-tipo-de-norma-wrapper [data-shs-level]'
                );
                let result = [];
                containers.forEach((c, i) => {
                    result.push(`Level ${c.dataset.shsLevel}: '${c.innerHTML.trim().substring(0, 300)}'`);
                });
                return result.join('\\n---\\n');
            }
        """)
        print(f"PGRH:\n{html_l2b}")

        # Try Drupal.ajax directly
        print("\n=== Probando Drupal.ajax directamente ===")
        await page.evaluate("""
            () => {
                // Try to trigger the SHS ajax callback
                if (typeof Drupal !== 'undefined' && Drupal.ajax) {
                    console.log('Drupal.ajax available');
                }
                // Find the ajax settings
                const settings = drupalSettings || {};
                console.log('drupalSettings keys:', Object.keys(settings).join(', '));
            }
        """)

        await asyncio.sleep(1)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
