"""Inspecciona un nodo normatividad existente: formato real del hidden input SHS.

Busca en /normatividad el primer nodo publicado, abre su /edit y lee:
- hidden input edit-field-tipo-de-norma (formato del valor guardado)
- hidden input edit-field-administrativo
- selects SHS presentes y su estado
NO guarda nada (cierra sin tocar).
"""
import asyncio, sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

from playwright.async_api import async_playwright

PROBE_JS = """() => {
    const out = {hidden: {}, selects: {}};
    for (const id of ['edit-field-tipo-de-norma', 'edit-field-administrativo']) {
        const h = document.getElementById(id);
        out.hidden[id] = h ? h.value : '(no existe)';
        if (h) out.hidden[id + '_attr'] = {name: h.name, shsSelector: h.getAttribute('data-shs-selector')};
    }
    for (const id of ['edit-field-tipo-de-norma-shs-0-0', 'edit-field-tipo-de-norma-shs-0-1',
                      'edit-field-administrativo-shs-0-0', 'edit-field-administrativo-shs-0-1']) {
        const s = document.getElementById(id);
        out.selects[id] = s ? `value=${s.value}` : '(no existe)';
    }
    out.title = document.querySelector('h1, .page-title')?.textContent?.trim() || '';
    out.url = location.href;
    return out;
}"""


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        print("🌐 Buscando nodos en /admin/content...")
        await page.goto("https://www.ana.gob.pe/admin/content",
                        wait_until="domcontentloaded", timeout=180000)
        await asyncio.sleep(5)

        # Primer enlace "Edit" con /node/XXXX/edit
        links = await page.eval_on_selector_all(
            "a[href*='/node/'][href*='/edit'], a[href*='/edit']",
            "els => els.map(e => e.getAttribute('href'))")
        edit_urls = [l for l in links if l and "/node/" in l and l.rstrip("/").endswith("/edit")]
        print(f"Enlaces a edit: {edit_urls[:8]}")

        if not edit_urls:
            print("❌ No se encontraron nodos editables en /admin/content")
            await context.close()
            return

        node_path = edit_urls[0].split("?")[0]
        edit_url = "https://www.ana.gob.pe" + node_path
        print(f"Abriendo edición: {edit_url}")
        await page.goto(edit_url, wait_until="domcontentloaded", timeout=180000)
        await asyncio.sleep(8)

        result = await page.evaluate(PROBE_JS)
        print(f"\n=== NODO EN EDICIÓN ===")
        print(f"Título: {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Hidden tipo-de-norma: {result['hidden'].get('edit-field-tipo-de-norma')!r}")
        print(f"  attr: {result['hidden'].get('edit-field-tipo-de-norma_attr')}")
        print(f"Hidden administrativo: {result['hidden'].get('edit-field-administrativo')!r}")
        print(f"  attr: {result['hidden'].get('edit-field-administrativo_attr')}")
        for k, v in result["selects"].items():
            print(f"Select {k}: {v}")

        await page.screenshot(path=str(ROOT / "logs" / "screenshots" / "nodo_existente_edit.png"),
                              full_page=True)
        print("\n✅ Screenshot guardado. Cerrando sin guardar.")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
