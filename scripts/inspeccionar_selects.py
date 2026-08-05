"""Inspecciona los valores disponibles en los selects cascada de Drupal."""
import asyncio
import io
import sys

# Fix Unicode output on Windows terminals
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

SELECTOR_NIVEL1 = "#edit-field-tipo-de-norma-shs-0-0"
SELECTOR_NIVEL2 = "#edit-field-tipo-de-norma-shs-0-1"
SELECTOR_AMBITO1 = "#edit-field-administrativo-shs-0-0"
SELECTOR_AMBITO2 = "#edit-field-administrativo-shs-0-1"


async def get_options(page, selector):
    """Devuelve lista de (value, text) de un select."""
    options = await page.eval_on_selector_all(
        f"{selector} option",
        "opts => opts.map(o => ({value: o.value, text: o.textContent.trim()}))"
    )
    return options


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            locale="es-PE",
        )
        page = await context.new_page()

        # Ir al formulario
        print("Navegando al formulario...")
        await page.goto("https://www.ana.gob.pe/node/add/normatividad",
                        wait_until="load", timeout=60000)

        # Si no está el formulario, esperar login
        titulo = await page.query_selector("#edit-title-0-value")
        if not titulo:
            print("\n⚠️  No se detectó el formulario. ¿Estás logueado?")
            print("Iniciá sesión y navegá a node/add/normatividad.")
            for i in range(100):
                await asyncio.sleep(3)
                titulo = await page.query_selector("#edit-title-0-value")
                if titulo:
                    print("[OK] Formulario detectado!")
                    break
                if i % 20 == 0:
                    print(f"  Esperando... ({i*3}s)")
            else:
                print("[ERROR] Timeout. Saliendo.")
                await context.close()
                return

        await asyncio.sleep(2)  # Dejar que Drupal termine de cargar

        # 1. Inspeccionar clasificación
        print("\n=== CLASIFICACIÓN - NIVEL 1 ===")
        opts1 = await get_options(page, SELECTOR_NIVEL1)
        for v, t in opts1:
            print(f"  value='{v}' -> {t}")

        # Seleccionar el que corresponde a "Resoluciones Emitidas por el ANA"
        # Buscar por texto
        for v, t in opts1:
            if "resoluciones emitidas" in t.lower():
                print(f"\n[OK] Seleccionando nivel 1: '{v}' = '{t}'")
                await page.select_option(SELECTOR_NIVEL1, v)
                break
        else:
            print("\n[ERROR] No se encontró 'Resoluciones Emitidas por el ANA' en nivel 1")
            await context.close()
            return

        # Esperar AJAX
        print("Esperando carga AJAX del nivel 2...")
        await asyncio.sleep(3)

        # 2. Inspeccionar nivel 2
        print("\n=== CLASIFICACIÓN - NIVEL 2 ===")
        opts2 = await get_options(page, SELECTOR_NIVEL2)
        for v, t in opts2:
            print(f"  value='{v}' -> {t}")

        # 3. Inspeccionar ámbito
        print("\n=== ÁMBITO ADMINISTRATIVO - NIVEL 1 ===")
        opts_a1 = await get_options(page, SELECTOR_AMBITO1)
        for v, t in opts_a1:
            print(f"  value='{v}' -> {t}")

        # Seleccionar AAA Madre de Dios
        for v, t in opts_a1:
            if "madre de dios" in t.lower():
                print(f"\n[OK] Seleccionando ámbito nivel 1: '{v}' = '{t}'")
                await page.select_option(SELECTOR_AMBITO1, v)
                break
        else:
            print("\n[ERROR] No se encontró 'AAA Madre de Dios' en ámbito nivel 1")

        await asyncio.sleep(3)

        print("\n=== ÁMBITO ADMINISTRATIVO - NIVEL 2 ===")
        opts_a2 = await get_options(page, SELECTOR_AMBITO2)
        for v, t in opts_a2:
            print(f"  value='{v}' -> {t}")

        print("\n[OK] Inspección completa. Copiá los valores correctos al field_map.json")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
