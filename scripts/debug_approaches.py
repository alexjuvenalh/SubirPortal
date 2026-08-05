import asyncio, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False, locale="es-PE")
        page = await context.new_page()

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        print("=== Approach 1: page.selectOption() + jQuery change ===")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")
        await page.evaluate("""
            jQuery('#edit-field-tipo-de-norma-shs-0-0').trigger('change');
            jQuery('#edit-field-tipo-de-norma-shs-0-0').trigger('shs:changed');
        """)
        await asyncio.sleep(5)
        l2_1 = await page.evaluate("""
            () => document.querySelector('[data-shs-level=\"1\"]')?.innerHTML || 'EMPTY'
        """)
        print(f"Level 2: {l2_1[:200]}")

        # Reload
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        print("\n=== Approach 2: Click on option (mousedown) ===")
        sel = page.locator("#edit-field-tipo-de-norma-shs-0-0")
        await sel.click()
        await asyncio.sleep(0.5)
        # The option with text containing "Resoluciones Emitidas por la ANA"
        opt = page.locator("#edit-field-tipo-de-norma-shs-0-0 option").filter(has_text="Emitidas por la ANA")
        await opt.click(force=True)
        await asyncio.sleep(5)
        l2_2 = await page.evaluate("""
            () => document.querySelector('[data-shs-level=\"1\"]')?.innerHTML || 'EMPTY'
        """)
        print(f"Level 2: {l2_2[:200]}")

        # Reload
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        print("\n=== Approach 3: dispatchEvent with MouseEvent ===")
        await page.evaluate("""
            () => {
                const sel = document.getElementById('edit-field-tipo-de-norma-shs-0-0');
                sel.value = '115';
                sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                sel.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                sel.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        await asyncio.sleep(5)
        l2_3 = await page.evaluate("""
            () => document.querySelector('[data-shs-level=\"1\"]')?.innerHTML || 'EMPTY'
        """)
        print(f"Level 2: {l2_3[:200]}")

        # Check if ANY new element appeared
        all_elems = await page.evaluate("""
            () => {
                const wrapper = document.getElementById('edit-field-tipo-de-norma-wrapper');
                return Array.from(wrapper.querySelectorAll('*')).map(e => e.tagName + 
                    (e.id ? '#' + e.id : '') + 
                    (e.className ? '.' + e.className.split(' ')[0] : '')
                ).slice(0, 30);
            }
        """)
        print(f"\nWrapper elements: {all_elems}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
