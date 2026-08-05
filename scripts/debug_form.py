"""Debug: inspecciona el formulario Drupal y guarda HTML."""
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

        print("Navegando...")
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        title = await page.title()
        url = page.url
        print(f"URL: {url}")
        print(f"Title: {title}")

        # Check if logged in
        has_form = await page.query_selector("#edit-title-0-value")
        has_login = await page.query_selector("#user-login-form")
        print(f"Formulario detectado: {bool(has_form)}")
        print(f"Login detectado: {bool(has_login)}")

        # Guardar screenshot
        await page.screenshot(path=str(ROOT / "logs" / "debug_form.png"), full_page=True)
        print("Screenshot: logs/debug_form.png")

        # Guardar HTML
        html = await page.content()
        (ROOT / "logs" / "debug_form.html").write_text(html, encoding="utf-8")
        print("HTML: logs/debug_form.html")

        # Buscar los selects
        for sel_id in ["edit-field-tipo-de-norma-shs-0-0",
                        "edit-field-tipo-de-norma-shs-0-1",
                        "edit-field-administrativo-shs-0-0",
                        "edit-field-administrativo-shs-0-1"]:
            el = await page.query_selector(f"#{sel_id}")
            if el:
                opts = await el.eval_on_selector_all("option", 
                    "opts => opts.map(o => ({value: o.value, text: o.textContent.trim()}))")
                print(f"\n{sel_id}: {len(opts)} opciones")
                for o in opts[:20]:  # first 20
                    print(f"  value='{o['value']}' -> {o['text'][:100]}")
            else:
                print(f"\n{sel_id}: NO ENCONTRADO")

        print("\n--- Esperando 30s por si hay login manual ---")
        for i in range(10):
            await asyncio.sleep(3)
            has_form = await page.query_selector("#edit-title-0-value")
            if has_form:
                print(f"[OK] Formulario detectado! Recargando opciones...")
                break

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
