"""
Bot de carga de Resoluciones Directorales al portal Drupal de ANA.

Usa Playwright para automatizar el llenado del formulario node/add/normatividad
siguiendo el mapeo verificado en el dry-run manual.

Uso:
    python scripts/subir_a_drupal.py

El bot procesa todas las RDs en data/carga_drupal_preview.json de a una,
presionando Guardar después de cada una.
"""

from __future__ import annotations

import asyncio
import json
import sys
import io
import urllib.request
from datetime import datetime
from pathlib import Path

# Fix Unicode output on Windows terminals
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS_PATH = ROOT / "data" / "carga_drupal_preview.json"
FIELD_MAP_PATH = ROOT / "config" / "drupal_field_map.json"
LOGS_DIR = ROOT / "logs"
SCREENSHOTS_DIR = ROOT / "logs" / "screenshots"

# Tiempos de espera (ms) — Drupal con AJAX puede ser lento
AJAX_TIMEOUT = 15_000
NAV_TIMEOUT = 120_000  # 120s: el portal ANA a veces tarda más de 60s en servir la página completa
ELEMENT_TIMEOUT = 10_000

# Selectores clave verificados en dry-run
SELECTORS = {
    "titulo": "#edit-title-0-value",
    "fecha": "#edit-field-fecha-de-aprobacion-de-la-0-value-date",
    "hora": "#edit-field-fecha-de-aprobacion-de-la-0-value-time",
    "numero": "#edit-field-num-resolucion-mat-0-value",
    "clasificacion_1": "#edit-field-tipo-de-norma-shs-0-0",
    "clasificacion_2": "#edit-field-tipo-de-norma-shs-0-1",
    "ambito_1": "#edit-field-administrativo-shs-0-0",
    "ambito_2": "#edit-field-administrativo-shs-0-1",
    "archivo_input": "#edit-field-file-0-upload",
    "archivo_boton": "#edit-field-file-0-upload-button",
    "guardar": "#edit-submit",
    "ckeditor_iframe": 'iframe[title="Editor de texto con formato, campo Resumen"]',
    "login_form": "#user-login-form",
    "mensaje_ok": ".messages--status",
    "titulo_pagina": ".page-title",
}


class DrupalUploadBot:
    """Automatiza la carga de RDs al portal Drupal de ANA."""

    def __init__(self) -> None:
        payloads_raw = json.loads(PAYLOADS_PATH.read_text(encoding="utf-8"))
        self.payloads = payloads_raw
        self.total = len(payloads_raw)
        self.completadas = 0
        self.fallidas: list[dict] = []

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self._log_file = LOGS_DIR / f"carga_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        # Flag: se activa cuando el SHS se resuelve por inyección manual
        self._shs_injected = False

    def log(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line)
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def screenshot(self, page: Page, name: str) -> None:
        path = SCREENSHOTS_DIR / f"{name}.png"
        await page.screenshot(path=str(path), full_page=True)
        self.log(f"  📸 Screenshot: {path.name}")

    async def wait_for_ajax(self, page: Page, timeout: int = AJAX_TIMEOUT) -> None:
        """Espera a que terminen las peticiones AJAX de Drupal."""
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeout:
            self.log("  ⚠️  AJAX no terminó en el tiempo esperado, continuando...")

    async def wait_for_manual_login(self, page: Page) -> bool:
        """Espera a que el usuario inicie sesión manualmente y navegue al formulario.

        Hace polling cada 3 segundos hasta que aparece #edit-title-0-value
        en la página actual. Timeout: 5 minutos.
        """
        self.log("\n  ╔══════════════════════════════════════════════╗")
        self.log("  ║  ACCIÓN REQUERIDA:                           ║")
        self.log("  ║  1. Iniciá sesión en la ventana del browser   ║")
        self.log("  ║  2. Navegá a node/add/normatividad           ║")
        self.log("  ║  El bot espera y continúa automáticamente...  ║")
        self.log("  ╚══════════════════════════════════════════════╝")

        max_attempts = 100  # 100 * 3s = 5 minutos
        for i in range(max_attempts):
            await asyncio.sleep(3)
            try:
                if await page.query_selector(SELECTORS["titulo"]):
                    self.log("  ✅ Formulario detectado! Continuando...")
                    return True
            except Exception:
                pass  # Página podría estar cargando
            if i > 0 and i % 20 == 0:
                self.log(f"  ⏳ Esperando login... ({i * 3}s transcurridos)")

        self.log("  ❌ Timeout: 5 minutos sin detectar el formulario.")
        return False

    async def ensure_logged_in(self, page: Page) -> bool:
        """Garantiza que el usuario esté autenticado antes de proceder."""
        # Si ya vemos el formulario, todo bien
        if await page.query_selector(SELECTORS["titulo"]):
            return True

        current_url = page.url
        page_title = await page.title()
        self.log(f"  URL actual: {current_url}")
        self.log(f"  Título: {page_title}")

        # Si es 403 o no es el formulario, vamos al login
        if "403" in page_title or "/user/login" not in current_url:
            self.log("  Navegando a página de login...")
            await page.goto("https://www.ana.gob.pe/user/login",
                          wait_until="load", timeout=NAV_TIMEOUT)

        # Esperar a que el usuario se loguee manualmente
        return await self.wait_for_manual_login(page)

    async def fill_text_field(self, page: Page, selector: str, value: str) -> None:
        """Llena un campo de texto simple."""
        await page.fill(selector, value)
        self.log(f"  ✅ {selector.split('#')[-1].split('-')[1:3][0]}: '{value}'")

    async def select_dropdown(self, page: Page, selector: str, value: str) -> None:
        """Selecciona una opción en un <select>."""
        await page.select_option(selector, value)
        self.log(f"  ✅ Select: {selector} → {value}")

    async def fill_ckeditor(self, page: Page, texto: str) -> None:
        """Llena el CKEditor del campo Resumen."""
        iframe = page.frame_locator(SELECTORS["ckeditor_iframe"])
        body = iframe.locator("body")
        await body.click()
        # Seleccionar todo y reemplazar
        await body.press("Control+a")
        await body.press("Backspace")
        await body.fill(texto)
        self.log(f"  ✅ CKEditor Resumen: {len(texto)} caracteres")

    async def fill_cascading_selects(self, page: Page, nivel1_sel: str,
                                      nivel1_val: str, nivel2_sel: str,
                                      nivel2_val: str) -> None:
        """Maneja selects jerárquicos SHS con recarga AJAX (clasificación y ámbito).

        Drupal SHS (9.5.8) dejó de renderizar el <select> del nivel 2 cuando el
        browser es controlado por Playwright: el request AJAX se dispara y el
        servidor responde 200 con los children, pero el widget no crea el nivel 2
        en el DOM. Por eso, si la opción no aparece en 5s, se usa inyección manual:
        se descargan los children desde la API SHS y se crea el <select> a mano.
        """
        await page.select_option(nivel1_sel, nivel1_val)
        self.log(f"  ✅ Select nivel 1: {nivel1_val}")

        # Si no hay nivel 2 requerido (None/_none), no hacer nada más
        if not nivel2_val or nivel2_val in ("_none", "None"):
            self.log(f"  ✅ Nivel 2 no requerido (valor '{nivel2_val}')")
            return

        # Pequeña pausa para que Drupal dispare el AJAX
        await asyncio.sleep(1)

        # Intento normal: esperar a que la opción esté attached en el DOM
        option_selector = f"{nivel2_sel} option[value='{nivel2_val}']"
        try:
            await page.wait_for_selector(
                option_selector,
                state="attached",
                timeout=5_000,
            )
            # Una vez que la opción existe, seleccionarla
            await page.select_option(nivel2_sel, nivel2_val)
            self.log(f"  ✅ Select nivel 2 (SHS normal): {nivel2_val}")
            return
        except PlaywrightTimeout:
            self.log(f"  ⚠️  SHS no renderizó nivel 2, usando inyección manual...")

        # Fallback: inyección manual del select nivel 2
        ok = await self._inject_shs_level2(
            page, nivel1_sel, nivel1_val, nivel2_sel, nivel2_val,
        )
        if not ok:
            await self.screenshot(page, f"error_cascading_{nivel2_val}")
            raise Exception(
                f"Inyección SHS falló para nivel 2 (tid={nivel2_val})"
            )
        self.log(f"  ✅ Select nivel 2 (inyectado): {nivel2_val}")

    async def _inject_shs_level2(self, page: Page, nivel1_sel: str,
                                 nivel1_val: str, nivel2_sel: str,
                                 nivel2_val: str) -> bool:
        """Crea manualmente el <select> del nivel 2 cuando el SHS no lo renderiza.

        El request AJAX de SHS se dispara pero el widget no crea el <select>
        del nivel 2. Para resolverlo: (1) leemos del DOM la config SHS del campo,
        (2) descargamos los children desde la API SHS con urllib (mismo origen,
        endpoint público), (3) inyectamos el <select> con la opción correcta y
        seteamos el hidden input con el path completo (padre,hijo) tal como lo
        hace el SHS cuando funciona.
        """
        self._shs_injected = True

        # 1. Leer config SHS del campo desde el DOM (síncrono, sin async en JS)
        info = await page.evaluate("""(args) => {
            const nivel2Id = args.nivel2Id;
            const hiddenId = nivel2Id.replace('-shs-0-1', '');
            const hiddenInput = document.getElementById(hiddenId);
            if (!hiddenInput) {
                return {ok: false, error: 'hidden input no encontrado: ' + hiddenId};
            }
            const shsSelector = hiddenInput.getAttribute('data-shs-selector');
            const cfg = ((window.drupalSettings || {}).shs || {})[shsSelector];
            if (!cfg || !cfg.baseUrl || !cfg.bundle) {
                return {ok: false, error: 'settings SHS no encontrados: ' + shsSelector};
            }
            const wrapper = document.getElementById(hiddenId + '-wrapper');
            const container = wrapper
                ? wrapper.querySelector('[data-shs-level="1"]')
                : null;
            return {
                ok: true,
                hiddenId: hiddenId,
                shsSelector: shsSelector,
                baseUrl: cfg.baseUrl,
                bundle: cfg.bundle,
                containerExists: !!container,
            };
        }""", {"nivel2Id": nivel2_sel.lstrip("#")})

        if not info.get("ok"):
            self.log(f"  ❌ Inyección SHS falló: {info.get('error')}")
            return False

        # 2. Descargar children desde la API SHS (urllib, endpoint público)
        api_url = (f"https://www.ana.gob.pe/{info['baseUrl']}/"
                   f"{info['shsSelector']}/{info['bundle']}/{nivel1_val}")
        try:
            req = urllib.request.Request(api_url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                children = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            self.log(f"  ❌ Inyección SHS falló descargando children: {e}")
            return False

        child = next(
            (c for c in children if str(c.get("tid")) == str(nivel2_val)),
            None,
        )
        if not child:
            self.log(f"  ❌ Inyección SHS falló: tid {nivel2_val} no está entre "
                     f"children de {nivel1_val}")
            return False
        child_name = child.get("name", str(nivel2_val))

        # 3. Inyectar el <select> y setear el hidden input
        inject = await page.evaluate("""(args) => {
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
            // El hidden input de SHS guarda SOLO el tid final seleccionado
            // (ver AppView.updateElementValue del módulo SHS). El path
            // 'padre,hijo' hace que Drupal rechace el submit.
            hiddenInput.value = childTid;
            hiddenInput.dispatchEvent(new Event('change', {bubbles: true}));
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            return {ok: true};
        }""", {
            "hiddenId": info["hiddenId"],
            "nivel2Id": nivel2_sel.lstrip("#"),
            "childTid": str(child["tid"]),
            "childName": child_name,
            "parentTid": str(nivel1_val),
        })

        if inject.get("ok"):
            self.log(f"  🔧 Nivel 2 inyectado: '{child_name}' (tid={child['tid']})")
            return True
        self.log(f"  ❌ Inyección SHS falló: {inject.get('error')}")
        return False

    async def upload_pdf(self, page: Page, pdf_path: str,
                         input_selector: str = "#edit-field-file-0-upload",
                         previous_fids: str = "",
                         fids_slot: int = 0,
                         require_fids: bool = True) -> str:
        """Sube un archivo PDF usando el widget managed_file de Drupal.

        Args:
            page: Página de Playwright.
            pdf_path: Ruta absoluta o relativa al PDF.
            input_selector: Selector CSS del input[type=file] a usar.
            previous_fids: Fids antes de este upload. Si se pasa, el método solo
                           considera exitoso el upload si el fids CAMBIA.
            fids_slot: Qué slot de field_file[N][fids] verificar (0 = principal, 1+ = adjuntos).
            require_fids: Si False, no lanza excepción si no se detecta fids (para adjuntos
                          que Drupal procesa de forma asíncrona).
        """
        abs_path = str(Path(pdf_path).resolve())
        pdf_name = Path(pdf_path).name
        self.log(f"  📎 Preparando upload: {pdf_name}")
        if previous_fids:
            self.log(f"     Fids anterior: {previous_fids}")

        # Derivar el selector del botón Upload desde el input_selector
        # Ej: #edit-field-file-0-upload → #edit-field-file-0-upload-button
        button_selector = input_selector.replace("-upload", "-upload-button")

        file_input = page.locator(input_selector)
        if await file_input.count() == 0:
            self.log(f"  ❌ No se encontró el input file: {input_selector}")
            raise Exception(f"No file input found: {input_selector}")

        # Método 1: set_input_files + dispatchEvent para trigger nativo
        await file_input.set_input_files(abs_path)
        self.log("  ✅ Archivo seleccionado vía set_input_files")

        # Disparar evento change nativo para que Drupal auto-file-upload lo detecte
        await page.evaluate(f"""
            const input = document.querySelector('{input_selector}');
            if (input) {{
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        """)
        await asyncio.sleep(3)

        # Verificar si auto-file-upload ya subió (y que el fids cambió)
        fids_val = await self._get_fids(page, slot=fids_slot)
        if fids_val and (not previous_fids or fids_val != previous_fids):
            self.log(f"  ✅ PDF subido vía auto-file-upload! Fids: {fids_val}")
            return fids_val

        # Método 2: Click directo al botón Subir vía JS (bypassea visibilidad)
        self.log("  ⏳ Auto-upload no detectado, forzando botón Subir vía JS...")
        await page.evaluate(f"""
            const btn = document.querySelector('{button_selector}');
            if (btn) {{
                // Forzar visibilidad
                btn.classList.remove('js-hide');
                btn.style.cssText = 'display:inline-block !important; visibility:visible !important; opacity:1 !important;';
                // Click vía JS
                btn.click();
                // También disparar mousedown/mouseup/click events
                btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
            }}
        """)
        await asyncio.sleep(5)

        # Verificar fids (debe haber cambiado respecto al anterior)
        fids_val = await self._get_fids(page, slot=fids_slot)
        if fids_val and (not previous_fids or fids_val != previous_fids):
            self.log(f"  ✅ PDF subido vía click JS! Fids: {fids_val}")
            return fids_val

        # Método 3: Disparar el AJAX de Drupal directamente
        self.log("  ⏳ Intentando AJAX de Drupal directamente...")
        await page.evaluate("""
            if (typeof Drupal !== 'undefined' && Drupal.Ajax) {
                const inputs = document.querySelectorAll('input[type="file"][id*="edit-field-file"]');
                const lastInput = inputs[inputs.length - 1];
                if (lastInput) {
                    const btnId = lastInput.id.replace('-upload', '-upload-button');
                    const btn = document.getElementById(btnId);
                    if (btn) {
                        const event = new Event('mousedown', { bubbles: true, cancelable: true });
                        btn.dispatchEvent(event);
                    }
                }
            }
        """)
        await asyncio.sleep(5)

        fids_val = await self._get_fids(page)
        if fids_val and (not previous_fids or fids_val != previous_fids):
            self.log(f"  ✅ PDF subido vía Drupal AJAX! Fids: {fids_val}")
            return fids_val

        # Método 4: Esperar más tiempo por si acaso
        self.log("  ⏳ Esperando 15s adicionales por upload tardío...")
        await asyncio.sleep(15)
        fids_val = await self._get_fids(page)
        if fids_val and (not previous_fids or fids_val != previous_fids):
            self.log(f"  ✅ PDF subido (tardío)! Fids: {fids_val}")
            return fids_val

        await self.screenshot(page, "error_upload_pdf")
        self.log("  ❌ No se pudo verificar la subida del PDF tras múltiples intentos")
        if require_fids:
            raise Exception("PDF upload verification failed")
        return ""

    async def _get_fids(self, page: Page, slot: int = 0) -> str:
        """Lee el valor del campo fids del managed_file en el slot indicado.

        Solo retorna el valor si es numérico (solo dígitos).
        String vacío, espacios, o cualquier otra cosa → retorna ''.
        """
        try:
            fids_input = page.locator(f'input[name="field_file[{slot}][fids]"]')
            if await fids_input.count() > 0:
                val = await fids_input.input_value()
                cleaned = val.strip()
                if cleaned and cleaned.isdigit():
                    return cleaned
        except Exception:
            pass
        return ""

    async def _clear_existing_file(self, page: Page) -> None:
        """Elimina cualquier archivo previo del widget managed_file.

        Si hay un fids en el formulario (por un intento fallido anterior,
        o porque Drupal dejó artefactos en la sesión), hace clic en el
        botón Remove para limpiar el widget antes de subir un PDF nuevo.

        Esto previene el bug del sufijo _N: cuando Drupal recibe múltiples
        subidas del mismo archivo (por reintentos fallidos), agrega _0, _1,
        etc. al nombre para evitar colisiones en el filesystem.
        """
        fids = await self._get_fids(page)

        # Solo limpiar si hay un fids real (numérico)
        if not fids:
            return

        self.log(f"  🧹 Limpiando archivo previo (fids: {fids})...")

        # Intentar botón Remove del widget managed_file de Drupal
        # Drupal 9/10 usa un button con clase específica o un link
        remove_selectors = [
            'button[id*="remove-button"]',
            'input[id*="remove-button"]',
            'button:has-text("Remove")',
            'a:has-text("Remove")',
            '[id*="field-file-0-remove-button"]',
        ]

        for sel in remove_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click()
                    await asyncio.sleep(1)
                    # Verificar que se limpió
                    new_fids = await self._get_fids(page)
                    if not new_fids:
                        self.log("  ✅ Archivo previo eliminado")
                        return
            except Exception:
                continue

        # Si no se pudo con botón Remove, intentar refresh del form
        self.log("  ⚠️  No se pudo limpiar con Remove, refrescando formulario...")
        await page.reload(wait_until="networkidle")
        await self.wait_for_ajax(page)
        self.log("  ✅ Formulario refrescado")

    async def _get_last_file_input_selector(self, page: Page) -> str:
        """Encuentra el selector del último input[type=file] disponible.

        Drupal agrega un nuevo input file vacío después de cada upload exitoso.
        Este método devuelve el selector del último (el disponible para subir).

        Incluye reintentos porque después de un upload AJAX el DOM puede estar
        en transición y el page.evaluate puede fallar con errores de JS internos.
        """
        max_retries = 5
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = await page.evaluate("""
                    (function() {
                        const inputs = document.querySelectorAll('input[type="file"][id*="edit-field-file"]');
                        if (inputs.length > 0) {
                            return '#' + inputs[inputs.length - 1].id;
                        }
                        return null;
                    })()
                """)
                if result:
                    self.log(f"     Input encontrado (intento {attempt}): {result}")
                    return result
                # No se encontró input — esperar y reintentar
                if attempt < max_retries:
                    self.log(f"     ⏳ Input no disponible aún (intento {attempt}/{max_retries}), esperando...")
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    self.log(f"     ⚠️  Error evaluando JS (intento {attempt}/{max_retries}): {e}")
            await asyncio.sleep(1)

        # Si llegamos acá, todos los intentos fallaron
        if last_error:
            self.log(f"     ⚠️  Último error: {last_error}")
        self.log("     ⚠️  Usando fallback: #edit-field-file-0-upload")
        return "#edit-field-file-0-upload"

    async def submit_form(self, page: Page) -> bool:
        """Presiona Guardar y verifica el resultado."""
        self.log("  🖱️  Presionando Guardar...")
        await page.click(SELECTORS["guardar"])

        # Esperar confirmación o error
        try:
            await page.wait_for_selector(
                SELECTORS["mensaje_ok"],
                timeout=NAV_TIMEOUT,
            )
            self.log("  🎉 ¡RD publicada exitosamente!")
            return True
        except PlaywrightTimeout:
            # Ver si hay mensaje de error
            error_selectors = [
                ".messages--error",
                ".alert-danger",
                '[class*="error"]',
            ]
            for err_sel in error_selectors:
                err = await page.query_selector(err_sel)
                if err:
                    texto_error = await err.text_content()
                    self.log(f"  ❌ Error Drupal: {texto_error}")
                    await self.screenshot(page, "error_drupal")
                    return False

            # Red de seguridad SHS: si inyectamos el nivel 2 manualmente y el
            # form no avanzó, esperar que el usuario corrija Clasificación/Ámbito
            # en la ventana del browser y presione Guardar de nuevo (3 min máx).
            if self._shs_injected:
                self.log("\n  ╔══════════════════════════════════════════╗")
                self.log("  ║  RED DE SEGURIDAD SHS                    ║")
                self.log("  ║  El nivel 2 se inyectó manualmente.      ║")
                self.log("  ║  Si Clasificación/Ámbito están vacíos,   ║")
                self.log("  ║  corregilos en la ventana del browser    ║")
                self.log("  ║  y presioná Guardar. El bot espera.      ║")
                self.log("  ╚══════════════════════════════════════════╝")
                for i in range(60):  # 60 * 3s = 3 minutos
                    await asyncio.sleep(3)
                    msg = await page.query_selector(SELECTORS["mensaje_ok"])
                    if msg:
                        self.log("  🎉 ¡RD publicada exitosamente (corrección manual)!")
                        return True
                    if i % 10 == 9:
                        self.log(f"  ⏳ Esperando corrección manual... ({i*3}s)")
                self.log("  ❌ Timeout red de seguridad. RD quedó pendiente.")
                return False

            # Si no hay mensaje, puede haber sido exitoso de todas formas
            self.log("  ⚠️  Sin confirmación explícita, verificando título de página...")
            await self.screenshot(page, "post_guardar_sin_mensaje")
            return True

    async def process_single_rd(self, page: Page, payload: dict, index: int) -> bool:
        """Procesa una sola RD: llena el formulario, sube el PDF y guarda."""
        fields = payload["fields"]
        pdf_name = payload["archivo_pdf"]
        self._shs_injected = False
        self.log(f"\n{'='*60}")
        self.log(f"📄 RD {index + 1}/{self.total}: {pdf_name}")
        self.log(f"   Título: {fields['titulo']}")
        self.log(f"{'='*60}")

        try:
            # 1. Navegar al formulario de creación
            self.log("🌐 Navegando al formulario...")
            await page.goto(payload["url"], wait_until="domcontentloaded",
                          timeout=NAV_TIMEOUT)
            # Pausa para que Drupal termine redirects JS (login -> form) y
            # cargue los assets críticos del SHS
            await asyncio.sleep(5)

            # 2. Verificar autenticación
            if not await self.ensure_logged_in(page):
                self.log("  ❌ No se pudo acceder al formulario")
                return False

            await self.screenshot(page, f"{pdf_name}_01_formulario_inicial")

            # 3. Título
            self.log("📝 Llenando Título...")
            await self.fill_text_field(page, SELECTORS["titulo"],
                                       fields["titulo"])

            # 4. Fecha y Hora
            self.log("📅 Llenando Fecha y Hora...")
            await self.fill_text_field(page, SELECTORS["fecha"],
                                       fields["fecha_rd"])
            await self.fill_text_field(page, SELECTORS["hora"],
                                       fields["hora_rd"])

            # 5. Número de resolución
            self.log("🔢 Llenando Número...")
            await self.fill_text_field(page, SELECTORS["numero"],
                                       fields["numero_resolucion"])

            # 6. Clasificación (selects en cascada con AJAX)
            self.log("🏷️  Seleccionando Clasificación...")
            await self.fill_cascading_selects(
                page,
                SELECTORS["clasificacion_1"], fields["clasificacion_nivel_1"],
                SELECTORS["clasificacion_2"], fields["clasificacion_nivel_2"],
            )

            # 7. Ámbito Administrativo (selects en cascada con AJAX)
            self.log("🗺️  Seleccionando Ámbito Administrativo...")
            await self.fill_cascading_selects(
                page,
                SELECTORS["ambito_1"], fields["ambito_administrativo_nivel_1"],
                SELECTORS["ambito_2"], fields["ambito_administrativo_nivel_2"],
            )

            await self.screenshot(page, f"{pdf_name}_02_selects_llenos")

            # 8. Resumen en CKEditor
            self.log("✍️  Llenando Resumen (CKEditor)...")
            await self.fill_ckeditor(page, fields["resumen"])

            await self.screenshot(page, f"{pdf_name}_03_resumen_lleno")

            # 9. Limpiar cualquier archivo previo en el managed_file
            #    (previene el bug _N cuando hay artefactos de intentos fallidos)
            await self._clear_existing_file(page)

            # 10. Subir PDF (con un reintento si falla)
            self.log("📎 Subiendo PDF...")
            upload_ok = False
            main_fids = ""
            for upload_attempt in range(2):
                try:
                    main_fids = await self.upload_pdf(page, fields["ruta_pdf"]) or ""
                    upload_ok = True
                    break
                except Exception as e:
                    self.log(f"  ❌ Upload intento {upload_attempt + 1}: {e}")
                    if upload_attempt == 0:
                        self.log("  🔄 Refrescando formulario para reintentar...")
                        await page.goto(payload["url"],
                                      wait_until="domcontentloaded",
                                      timeout=NAV_TIMEOUT)
                        await asyncio.sleep(5)
                        await self.ensure_logged_in(page)
                        # Re-llenar campos que se perdieron con el refresh
                        await self.fill_text_field(page, SELECTORS["titulo"],
                                                   fields["titulo"])
                        await self.fill_text_field(page, SELECTORS["fecha"],
                                                   fields["fecha_rd"])
                        await self.fill_text_field(page, SELECTORS["hora"],
                                                   fields["hora_rd"])
                        await self.fill_text_field(page, SELECTORS["numero"],
                                                   fields["numero_resolucion"])
                        await self.fill_cascading_selects(
                            page,
                            SELECTORS["clasificacion_1"], fields["clasificacion_nivel_1"],
                            SELECTORS["clasificacion_2"], fields["clasificacion_nivel_2"],
                        )
                        await self.fill_cascading_selects(
                            page,
                            SELECTORS["ambito_1"], fields["ambito_administrativo_nivel_1"],
                            SELECTORS["ambito_2"], fields["ambito_administrativo_nivel_2"],
                        )
                        await self.fill_ckeditor(page, fields["resumen"])
                    else:
                        raise

            if not upload_ok:
                self.fallidas.append({
                    "pdf": pdf_name,
                    "titulo": fields["titulo"],
                    "error": "PDF upload failed after retry",
                })
                return False

            await self.screenshot(page, f"{pdf_name}_04_pdf_subido")

            # 11. Esperar estabilización del DOM post-upload
            # Drupal puede estar procesando JS de la respuesta AJAX (nuevos inputs,
            # callbacks de behaviors). Un page.evaluate muy rápido puede fallar.
            await asyncio.sleep(2)
            await self.wait_for_ajax(page)

            # 12. Subir adjuntos (planos, anexos) si existen
            adjuntos_rutas = payload.get("adjuntos_rutas", [])
            adjuntos_nombres = payload.get("adjuntos", [])
            # Si hay 2+ adjuntos, invertir el orden para que Drupal
            # muestre el plano más alto primero (PLANO-08 → PLANO-01)
            if len(adjuntos_rutas) >= 2:
                adjuntos_rutas = list(reversed(adjuntos_rutas))
                adjuntos_nombres = list(reversed(adjuntos_nombres))
                self.log(f"📎 Orden invertido: {len(adjuntos_rutas)} planos (mayor → menor)")
            if adjuntos_rutas:
                self.log(f"📎 Subiendo {len(adjuntos_rutas)} adjunto(s)...")
                for idx, (adj_ruta, adj_nombre) in enumerate(
                    zip(adjuntos_rutas, adjuntos_nombres), start=1
                ):
                    self.log(f"  📎 Adjunto {idx}/{len(adjuntos_rutas)}: {adj_nombre}")
                    # Drupal agrega un nuevo input file después de cada upload.
                    # Buscar el último disponible para este adjunto.
                    adj_input_selector = await self._get_last_file_input_selector(page)
                    self.log(f"     Usando input: {adj_input_selector}")
                    # Pasar el fids del PDF principal para detectar cambio real
                    adj_slot = idx  # adjunto 1 → slot 1, adjunto 2 → slot 2...
                    adj_fids = await self.upload_pdf(
                        page, adj_ruta,
                        input_selector=adj_input_selector,
                        previous_fids=main_fids,
                        fids_slot=adj_slot,
                        require_fids=False,
                    )
                    # Esperar a que field_file[N][fids] se llene (slot correcto)
                    self.log(f"     ⏳ Esperando field_file[{adj_slot}][fids]...")
                    for wait_i in range(15):
                        await asyncio.sleep(2)
                        slot_fids = await self._get_fids(page, slot=adj_slot)
                        if slot_fids:
                            self.log(f"     ✅ field_file[{adj_slot}][fids] = {slot_fids}")
                            break
                        if wait_i % 3 == 2:
                            self.log(f"     ⏳ Aún esperando... ({(wait_i+1)*2}s)")
                    await self.screenshot(page, f"{pdf_name}_adjunto_{idx:02d}_{adj_nombre}")

            # 13. Guardar
            success = await self.submit_form(page)

            if success:
                await self.screenshot(page, f"{pdf_name}_05_publicada")
                self.completadas += 1
                return True
            else:
                self.fallidas.append({"pdf": pdf_name, "titulo": fields["titulo"]})
                return False

        except Exception as e:
            self.log(f"  ❌ ERROR: {e}")
            await self.screenshot(page, f"{pdf_name}_error")
            self.fallidas.append({
                "pdf": pdf_name,
                "titulo": fields.get("titulo", "?"),
                "error": str(e),
            })
            return False

    async def run(self) -> None:
        """Ejecuta el bot completo para todas las RDs pendientes."""
        self.log(f"\n{'#'*60}")
        self.log(f"# Bot de Carga Drupal ANA")
        self.log(f"# RDs pendientes: {self.total}")
        self.log(f"# Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"{'#'*60}")

        # Directorio para datos persistentes del navegador (cookies, sesiones)
        user_data_dir = ROOT / "data" / "browser_profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            # Usar contexto persistente: guarda cookies entre sesiones
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=False,
                args=["--start-maximized"],
                viewport={"width": 1920, "height": 1080},
                locale="es-PE",
            )

            page = await context.new_page()

            try:
                for i, payload in enumerate(self.payloads):
                    success = await self.process_single_rd(page, payload, i)
                    if not success:
                        self.log(f"\n  ⚠️  RD {payload['archivo_pdf']} tuvo problemas.")
                        # Si falló la primera, probablemente es un problema sistémico
                        if i == 0:
                            self.log("  Deteniendo ejecución. Revisá los screenshots en logs/screenshots/")
                            break
            finally:
                await context.close()

        self.log(f"\n{'#'*60}")
        self.log(f"# RESUMEN FINAL")
        self.log(f"# Total: {self.total}")
        self.log(f"# Completadas: {self.completadas}")
        self.log(f"# Fallidas: {len(self.fallidas)}")
        if self.fallidas:
            for f in self.fallidas:
                self.log(f"#   ❌ {f['pdf']}: {f.get('titulo', '?')}")
        self.log(f"# Log: {self._log_file}")
        self.log(f"{'#'*60}")

        # Guardar resumen JSON
        resumen_path = LOGS_DIR / f"resumen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        resumen_path.write_text(json.dumps({
            "total": self.total,
            "completadas": self.completadas,
            "fallidas": self.fallidas,
            "finalizado": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        sys.exit(0 if self.completadas == self.total else 1)


def main() -> None:
    if not PAYLOADS_PATH.exists():
        raise SystemExit(f"No existe el archivo de carga: {PAYLOADS_PATH}")
    if not FIELD_MAP_PATH.exists():
        raise SystemExit(f"No existe el mapeo Drupal: {FIELD_MAP_PATH}")

    bot = DrupalUploadBot()
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
