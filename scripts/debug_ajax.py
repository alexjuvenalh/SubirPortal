"""Debug: probar diferentes formas de disparar el AJAX de SHS."""
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

        print("Seleccionando nivel 1 con dispatchEvent change...")
        
        # Select the option and force a change event with full event init
        await page.evaluate("""
            () => {
                const sel = document.getElementById('edit-field-tipo-de-norma-shs-0-0');
                sel.value = '115';
                // Dispatch multiple events that Drupal might listen for
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('blur', { bubbles: true }));
                // Also try Drupal-specific events
                if (typeof jQuery !== 'undefined') {
                    jQuery(sel).trigger('change');
                    jQuery(sel).trigger('shs:changed');
                }
            }
        """)

        print("Esperando 8s para AJAX...")
        await asyncio.sleep(8)

        # Check what's in the level 2 container now
        html_l2 = await page.evaluate("""
            () => {
                const container = document.querySelector('#edit-field-tipo-de-norma-wrapper [data-shs-level="1"]');
                return container ? container.innerHTML : 'CONTAINER NOT FOUND';
            }
        """)
        print(f"\nContenido nivel 2 container:\n{html_l2[:1000]}")

        # Also check if a new select appeared anywhere
        selects = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll(
                    '#edit-field-tipo-de-norma-wrapper select'
                )).map(s => ({id: s.id, options: s.options.length}));
            }
        """)
        print(f"\nSelects en el wrapper: {selects}")

        # Check the hidden input value
        hidden_val = await page.evaluate("""
            () => document.getElementById('edit-field-tipo-de-norma').value
        """)
        print(f"Hidden input value: '{hidden_val}'")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
