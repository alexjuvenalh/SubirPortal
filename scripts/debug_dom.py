"""Debug: ver que elementos nuevos aparecen tras seleccionar nivel 1."""
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

        # Check what exists before selecting
        print("=== ANTES de seleccionar nivel 1 ===")
        before = await page.query_selector_all("[id*='field-tipo-de-norma']")
        print(f"Elementos con id*='field-tipo-de-norma': {len(before)}")
        for el in before:
            tag = await el.evaluate("el => el.tagName")
            eid = await el.get_attribute("id")
            name = await el.get_attribute("name")
            print(f"  <{tag}> id='{eid}' name='{name}'")

        # Also look for shs widgets
        shs_before = await page.query_selector_all("[class*='shs']")
        print(f"\nElementos con class*='shs': {len(shs_before)}")
        for el in shs_before:
            tag = await el.evaluate("el => el.tagName")
            eid = await el.get_attribute("id")
            cls = await el.get_attribute("class")
            print(f"  <{tag}> id='{eid}' class='{cls[:100]}'")

        # Select nivel 1
        print("\n=== Seleccionando nivel 1: '115' ===")
        await page.select_option("#edit-field-tipo-de-norma-shs-0-0", "115")
        await asyncio.sleep(5)

        # Check what exists AFTER
        print("\n=== DESPUES de seleccionar nivel 1 ===")
        after = await page.query_selector_all("[id*='field-tipo-de-norma']")
        print(f"Elementos con id*='field-tipo-de-norma': {len(after)}")
        for el in after:
            tag = await el.evaluate("el => el.tagName")
            eid = await el.get_attribute("id")
            name = await el.get_attribute("name")
            cls = await el.get_attribute("class") or ""
            print(f"  <{tag}> id='{eid}' name='{name}' class='{cls[:120]}'")

        shs_after = await page.query_selector_all("[class*='shs']")
        print(f"\nElementos con class*='shs': {len(shs_after)}")
        for el in shs_after:
            tag = await el.evaluate("el => el.tagName")
            eid = await el.get_attribute("id")
            cls = await el.get_attribute("class")
            print(f"  <{tag}> id='{eid}' class='{cls[:100]}'")

        # Also save full HTML snippet around the field
        field_wrapper = await page.query_selector("#edit-field-tipo-de-norma-wrapper")
        if field_wrapper:
            html = await field_wrapper.inner_html()
            (ROOT / "logs" / "debug_wrapper.html").write_text(html, encoding="utf-8")
            print(f"\nHTML del wrapper guardado en logs/debug_wrapper.html")
            print(f"Primeros 2000 chars del wrapper:")
            print(html[:2000])

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
