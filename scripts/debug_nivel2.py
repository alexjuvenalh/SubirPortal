"""Debug nivel 2: seleccionar nivel 1 y ver opciones del cascada."""
import asyncio
import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]


async def get_options(page, selector):
    el = await page.query_selector(selector)
    if not el:
        return []
    return await el.eval_on_selector_all("option",
        "opts => opts.map(o => ({value: o.value, text: o.textContent.trim()}))")


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            locale="es-PE",
        )
        page = await context.new_page()

        print("Navegando...")
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        # 1. Clasificacion: seleccionar nivel 1 = 115
        print("\n--- CLASIFICACION ---")
        print("Seleccionando nivel 1: '115' (Resoluciones Emitidas por la ANA)...")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")

        # Esperar AJAX
        print("Esperando 5s para carga AJAX...")
        await asyncio.sleep(5)

        # Ver nivel 2
        opts = await get_options(page, "#edit-field-tipo-de-norma-shs-0-1")
        print(f"\nNivel 2 ({len(opts)} opciones):")
        for o in opts:
            marker = " <--- BUSCAMOS ESTA?" if "autoridades administrativas" in o['text'].lower() else ""
            print(f"  value='{o['value']}' -> {o['text']}{marker}")

        if not opts:
            print("  (vacio - el select nivel 2 no aparecio)")
            # Intentar con state:attached
            sel = await page.query_selector("#edit-field-tipo-de-norma-shs-0-1")
            print(f"  Selector existe: {bool(sel)}")
            if sel:
                html = await sel.inner_html()
                print(f"  Inner HTML: {html[:500]}")

        # 2. Ambito: seleccionar nivel 1 = 17
        print("\n--- AMBITO ADMINISTRATIVO ---")
        print("Seleccionando nivel 1: '17' (AAA Madre de Dios)...")
        await page.select_option("#edit-field-administrativo-shs-0-0", "17")

        print("Esperando 5s para carga AJAX...")
        await asyncio.sleep(5)

        opts_a = await get_options(page, "#edit-field-administrativo-shs-0-1")
        print(f"\nNivel 2 ({len(opts_a)} opciones):")
        for o in opts_a:
            print(f"  value='{o['value']}' -> {o['text']}")

        if not opts_a:
            sel = await page.query_selector("#edit-field-administrativo-shs-0-1")
            print(f"  Selector existe: {bool(sel)}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
