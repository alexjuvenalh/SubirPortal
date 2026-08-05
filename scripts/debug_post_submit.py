"""Diagnóstico: capturar el error Drupal post-submit con la inyección SHS.

Reproduce el flujo del bot para la primera RD, presiona Guardar y captura:
1. Todos los mensajes de error en el DOM (selectores amplios)
2. Valores del hidden input y selects SHS post-submit
3. Screenshot
No publica nada si el submit es rechazado; si Drupal aceptara, NO crea el nodo
para no duplicar (cancela: simplemente no presiona de nuevo).
"""
import asyncio, io, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# subir_a_drupal ya envuelve sys.stdout en win32 al importarse.
from playwright.async_api import async_playwright
from subir_a_drupal import DrupalUploadBot, SELECTORS, NAV_TIMEOUT

ERROR_PROBE_JS = """() => {
    const out = {errors: [], hidden: {}, shsSelects: {}, status: [], warnings: []};
    // 1. Todos los posibles mensajes de error
    const selectors = [
        '.messages--error', '.alert-danger', '[class*="error"]',
        '.form-item--error-message', '.form-item__error-message',
        '.form-item__error', '.form-error', 'div.error',
        '.form-item--error', 'input[aria-invalid="true"]',
        'select[aria-invalid="true"]', '.messages--warning', '.messages--status',
        '.messages'
    ];
    const seen = new Set();
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const tag = el.tagName.toLowerCase();
            const id = el.id ? '#' + el.id : '';
            const cls = (el.className || '').toString();
            const txt = (el.textContent || '').trim().replace(/\\s+/g, ' ');
            if (cls.includes('messages--status')) out.status.push(txt.slice(0, 200));
            else if (cls.includes('messages--warning')) out.warnings.push(txt.slice(0, 200));
            else if (txt) out.errors.push({sel, tag, id, cls: cls.slice(0, 60), txt: txt.slice(0, 200)});
        }
    }
    // 2. Buscar texto de error de validación Drupal en cualquier parte
    const body = document.body.textContent || '';
    for (const needle of ['obligatorio', 'required', 'Por favor', 'debe seleccionar', 'es requerido']) {
        if (body.toLowerCase().includes(needle.toLowerCase())) {
            out.errors.push({sel: 'text-search', tag: 'body', id: '', cls: '', txt: `Contiene '${needle}'`});
        }
    }
    // 3. Hidden inputs y selects SHS
    for (const id of ['edit-field-tipo-de-norma', 'edit-field-administrativo']) {
        const h = document.getElementById(id);
        out.hidden[id] = h ? h.value : '(no existe)';
    }
    for (const id of ['edit-field-tipo-de-norma-shs-0-0', 'edit-field-tipo-de-norma-shs-0-1',
                      'edit-field-administrativo-shs-0-0', 'edit-field-administrativo-shs-0-1']) {
        const s = document.getElementById(id);
        out.shsSelects[id] = s ? `value=${s.value}` : '(no existe)';
    }
    // 4. Estado del form actual
    out.url = location.href;
    out.hasSubmitBtn = !!document.getElementById('edit-submit');
    return out;
}"""


async def main():
    bot = DrupalUploadBot()
    payload = bot.payloads[0]
    fields = payload["fields"]
    pdf_name = payload["archivo_pdf"]
    bot.log(f"\nDIAGNÓSTICO para: {pdf_name}")

    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            args=["--start-maximized"],
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        bot._shs_injected = False
        bot.log("🌐 Navegando al formulario...")
        await page.goto(payload["url"], wait_until="domcontentloaded",
                        timeout=NAV_TIMEOUT)
        await asyncio.sleep(5)
        await bot.ensure_logged_in(page)

        # Llenar igual que el bot
        await bot.fill_text_field(page, SELECTORS["titulo"], fields["titulo"])
        await bot.fill_text_field(page, SELECTORS["fecha"], fields["fecha_rd"])
        await bot.fill_text_field(page, SELECTORS["hora"], fields["hora_rd"])
        await bot.fill_text_field(page, SELECTORS["numero"], fields["numero_resolucion"])
        await bot.fill_cascading_selects(
            page, SELECTORS["clasificacion_1"], fields["clasificacion_nivel_1"],
            SELECTORS["clasificacion_2"], fields["clasificacion_nivel_2"])
        # EXPERIMENTO: sobrescribir el hidden con SOLO el tid final (formato del JS SHS)
        bot.log("🔬 EXPERIMENTO: hidden tipo-de-norma = '129' (solo tid final)")
        await page.evaluate("""() => {
            const h = document.getElementById('edit-field-tipo-de-norma');
            h.value = '129';
            h.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        await bot.fill_cascading_selects(
            page, SELECTORS["ambito_1"], fields["ambito_administrativo_nivel_1"],
            SELECTORS["ambito_2"], fields["ambito_administrativo_nivel_2"])
        await bot.fill_ckeditor(page, fields["resumen"])
        await bot._clear_existing_file(page)

        # Estado ANTES de guardar
        antes = await page.evaluate(ERROR_PROBE_JS)
        bot.log(f"\n=== ANTES DE GUARDAR ===")
        bot.log(f"hidden: {antes['hidden']}")
        bot.log(f"shsSelects: {antes['shsSelects']}")

        # Presionar Guardar y esperar un poco (capturando el POST)
        bot.log("\n🖱️  Presionando Guardar (diagnóstico)...")
        post_bodies = []

        async def on_request(request):
            if request.method == "POST":
                pd = request.post_data
                if pd and ("tipo_de_norma" in pd or "administrativo" in pd):
                    post_bodies.append({"url": request.url, "post": pd[:6000]})

        page.on("request", on_request)
        await page.click(SELECTORS["guardar"])
        bot.log("⏳ Esperando 45s la respuesta de Drupal...")
        await asyncio.sleep(45)

        bot.log(f"\n=== POST CAPTURADOS ({len(post_bodies)}) ===")
        for pb in post_bodies[:3]:
            bot.log(f"URL: {pb['url']}")
            bot.log(f"POST: {pb['post']}")
            bot.log("---")

        despues = await page.evaluate(ERROR_PROBE_JS)
        bot.log(f"\n=== DESPUÉS DE GUARDAR (45s) ===")
        bot.log(f"URL: {despues['url']}")
        bot.log(f"hidden: {despues['hidden']}")
        bot.log(f"shsSelects: {despues['shsSelects']}")
        bot.log(f"hasSubmitBtn: {despues['hasSubmitBtn']}")
        if despues["status"]:
            bot.log(f"\n✅ MENSAJES DE ÉXITO ({len(despues['status'])}):")
            for s in despues["status"]:
                bot.log(f"  [status] {s}")
        if despues["warnings"]:
            bot.log(f"\n⚠️ WARNINGS ({len(despues['warnings'])}):")
            for w in despues["warnings"]:
                bot.log(f"  [warning] {w}")
        if despues["errors"]:
            bot.log(f"\nERRORES DETECTADOS ({len(despues['errors'])}):")
            for e in despues["errors"][:25]:
                bot.log(f"  [{e['sel']}|{e['tag']}{e['id']}|{e['cls']}] {e['txt'][:200]}")
        else:
            bot.log("\n⚠️  NO se detectaron mensajes de error en los selectores buscados.")

        await bot.screenshot(page, "diag_post_submit")
        bot.log("\n✅ Diagnóstico completo. Revisar screenshots.")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
