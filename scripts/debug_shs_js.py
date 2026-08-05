"""Lista los recursos SHS cargados en el form y descarga el JS del widget para
analizar cómo construye el valor del hidden input."""
import asyncio, sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

from playwright.async_api import async_playwright


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="domcontentloaded", timeout=180000)
        await asyncio.sleep(5)

        # Listar recursos con 'shs'
        resources = await page.evaluate("""() =>
            performance.getEntriesByType('resource')
                .map(e => e.name)
                .filter(n => n.includes('shs'))""")
        print("Recursos SHS:")
        for r in resources:
            print(" ", r)

        # Buscar el selector SHS y su config en drupalSettings
        cfg = await page.evaluate("""() => {
            const shs = (window.drupalSettings || {}).shs || {};
            const out = {};
            for (const [k, v] of Object.entries(shs)) {
                out[k] = {bundle: v.bundle, baseUrl: v.baseUrl,
                          cardinality: v.cardinality,
                          defaultValue: v.defaultValue,
                          parents: v.parents,
                          settings: v.settings ? Object.keys(v.settings) : [],
                          classes: v.classes};
            }
            return out;
        }""")
        print("\ndrupalSettings.shs:")
        import json
        print(json.dumps(cfg, ensure_ascii=False, indent=2))

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
