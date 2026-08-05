"""Probar bypass del SHS: setear el hidden input directamente."""
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

        # Try different formats for bypassing SHS
        # Format 1: just the leaf term ID
        print("=== Probando formato: '129' (leaf ID) ===")
        await page.evaluate("""
            () => {
                const input = document.getElementById('edit-field-tipo-de-norma');
                input.value = '129';
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        """)
        await asyncio.sleep(2)
        val = await page.evaluate("""() => document.getElementById('edit-field-tipo-de-norma').value""")
        print(f"  Hidden value: '{val}'")

        # Check if SHS widget reflects it
        l1 = await page.evaluate("""() => document.getElementById('edit-field-tipo-de-norma-shs-0-0')?.value""")
        print(f"  Nivel 1 select value: '{l1}'")

        # Format 2: space-separated path
        print("\n=== Probando formato: '115 129' (path) ===")
        await page.evaluate("""
            () => {
                const input = document.getElementById('edit-field-tipo-de-norma');
                input.value = '115 129';
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('input', { bubbles: true }));
            }
        """)
        await asyncio.sleep(2)
        val = await page.evaluate("""() => document.getElementById('edit-field-tipo-de-norma').value""")
        print(f"  Hidden value: '{val}'")

        # Format 3: comma-separated
        print("\n=== Probando formato: '115,129' (comma) ===")
        await page.evaluate("""
            () => {
                const input = document.getElementById('edit-field-tipo-de-norma');
                input.value = '115,129';
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        await asyncio.sleep(2)
        val = await page.evaluate("""() => document.getElementById('edit-field-tipo-de-norma').value""")
        print(f"  Hidden value: '{val}'")

        # Also check ambito
        print("\n=== Ambito: probando formatos ===")
        formats = ['17', '17 16', '17,16', '17/16']
        for fmt in formats:
            await page.evaluate(f"""
                () => {{
                    const input = document.getElementById('edit-field-administrativo');
                    input.value = '{fmt}';
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            await asyncio.sleep(1)
            val = await page.evaluate("""() => document.getElementById('edit-field-administrativo').value""")
            print(f"  '{fmt}' -> hidden: '{val}'")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
