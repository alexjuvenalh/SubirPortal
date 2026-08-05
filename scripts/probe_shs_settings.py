import asyncio, io, sys, json
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
        await asyncio.sleep(4)

        info = await page.evaluate("""
            () => {
                const shs = (window.drupalSettings || {}).shs || {};
                return {
                    tipo_de_norma: shs['shs-field-tipo-de-norma'],
                    administrativo: shs['shs-field-administrativo']
                };
            }
        """)
        for field, data in info.items():
            print(f"=== {field} ===")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print()
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
