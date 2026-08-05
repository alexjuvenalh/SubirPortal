import asyncio, io, sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

# Replicar el método de inyección para probarlo aislado
INJECT_JS_INFO = """(args) => {
    const nivel2Id = args.nivel2Id;
    const hiddenId = nivel2Id.replace('-shs-0-1', '');
    const hiddenInput = document.getElementById(hiddenId);
    if (!hiddenInput) return {ok: false, error: 'hidden input no encontrado: ' + hiddenId};
    const shsSelector = hiddenInput.getAttribute('data-shs-selector');
    const cfg = ((window.drupalSettings || {}).shs || {})[shsSelector];
    if (!cfg || !cfg.baseUrl || !cfg.bundle) return {ok: false, error: 'settings SHS no encontrados'};
    return {ok: true, hiddenId: hiddenId, shsSelector: shsSelector, baseUrl: cfg.baseUrl, bundle: cfg.bundle};
}"""

INJECT_JS_SET = """(args) => {
    const {hiddenId, nivel2Id, childTid, childName, parentTid} = args;
    const wrapper = document.getElementById(hiddenId + '-wrapper');
    if (!wrapper) return {ok: false, error: 'wrapper no encontrado'};
    const container = wrapper.querySelector('[data-shs-level="1"]');
    if (!container) return {ok: false, error: 'container nivel 2 no encontrado'};
    container.innerHTML = '';
    const sel = document.createElement('select');
    sel.id = nivel2Id;
    sel.className = 'shs-select form-select form-element form-element--type-select';
    const opt = document.createElement('option');
    opt.value = childTid;
    opt.textContent = childName;
    sel.appendChild(opt);
    container.appendChild(sel);
    sel.value = childTid;
    const hiddenInput = document.getElementById(hiddenId);
    hiddenInput.value = parentTid + ',' + childTid;
    hiddenInput.dispatchEvent(new Event('change', {bubbles: true}));
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    return {ok: true};
}"""


def fetch_children(selector, bundle, parent_tid):
    import urllib.request, json
    url = f"https://www.ana.gob.pe/{selector.split('/')[-1]}/{bundle}/{parent_tid}"
    # construir correctamente: baseUrl + shsSelector + bundle + parent
    url = f"https://www.ana.gob.pe/shs-term-data/{selector}/{bundle}/{parent_tid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False, locale="es-PE")
        page = await context.new_page()
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="domcontentloaded", timeout=180000)
        await asyncio.sleep(8)

        # ==== Test CLASIFICACION ====
        print("=== CLASIFICACION: seleccionar nivel 1=115, inyectar nivel 2=129 ===")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")
        await asyncio.sleep(2)

        info = await page.evaluate(INJECT_JS_INFO, {"nivel2Id": "edit-field-tipo-de-norma-shs-0-1"})
        print(f"Config: {info}")

        children = fetch_children(info["shsSelector"], info["bundle"], "115")
        child = next((c for c in children if str(c["tid"]) == "129"), None)
        print(f"Child 129: {child}")

        result = await page.evaluate(INJECT_JS_SET, {
            "hiddenId": info["hiddenId"],
            "nivel2Id": "edit-field-tipo-de-norma-shs-0-1",
            "childTid": str(child["tid"]),
            "childName": child["name"],
            "parentTid": "115",
        })
        print(f"Inject result: {result}")

        # Verificar
        hidden = await page.evaluate("document.getElementById('edit-field-tipo-de-norma').value")
        sel_opt = await page.evaluate("document.getElementById('edit-field-tipo-de-norma-shs-0-1')?.value")
        print(f"Hidden input: '{hidden}' | select nivel 2 value: '{sel_opt}'")

        # ==== Test AMBITO ====
        print("\n=== AMBITO: seleccionar nivel 1=17 (nivel 2 no requerido) ===")
        await page.select_option("#edit-field-administrativo-shs-0-0", "17")
        await asyncio.sleep(2)
        hidden_adm = await page.evaluate("document.getElementById('edit-field-administrativo').value")
        print(f"Hidden input ámbito: '{hidden_adm}'")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
