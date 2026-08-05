import asyncio, io, sys
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

        # Fill basics
        await page.fill("#edit-title-0-value", "RD N 0206-2026-ANA-AAA.MDD")
        await page.fill("#edit-field-fecha-de-aprobacion-de-la-0-value-date", "2026-07-30")
        await page.fill("#edit-field-fecha-de-aprobacion-de-la-0-value-time", "08:00:00")
        await page.fill("#edit-field-num-resolucion-mat-0-value", "206")
        print("Basics filled")

        # Bypass SHS: set hidden classification to 129
        await page.evaluate("""
            document.getElementById('edit-field-tipo-de-norma').value = '129';
            document.getElementById('edit-field-tipo-de-norma').dispatchEvent(
                new Event('change', { bubbles: true }));
        """)
        await asyncio.sleep(1)
        val = await page.evaluate("document.getElementById('edit-field-tipo-de-norma').value")
        print(f"Clasificacion hidden = {val}")

        # Bypass SHS: set hidden ambito to 17
        await page.evaluate("""
            document.getElementById('edit-field-administrativo').value = '17';
            document.getElementById('edit-field-administrativo').dispatchEvent(
                new Event('change', { bubbles: true }));
        """)
        await asyncio.sleep(1)
        val2 = await page.evaluate("document.getElementById('edit-field-administrativo').value")
        print(f"Ambito hidden = {val2}")

        # Fill CKEditor resumen
        iframe = page.frame_locator('iframe[title*="Resumen"]')
        body = iframe.locator("body")
        await body.click()
        await body.press("Control+a")
        await body.press("Backspace")
        await body.fill("ARTICULO 1.- ACREDITAR la disponibilidad hidrica.")
        print("Resumen filled")

        # Upload PDF
        pdf_path = str(ROOT / "pdfs" / "nuevos" / "59-RD-0206-2026-05.pdf")
        file_input = page.locator("#edit-field-file-0-upload")
        await file_input.set_input_files(pdf_path)
        print("PDF uploaded")
        await asyncio.sleep(3)

        # Screenshot before submit
        await page.screenshot(path=str(ROOT / "logs" / "test_bypass.png"), full_page=True)
        print("Screenshot: logs/test_bypass.png")

        # Click Guardar
        print("Clicking Guardar...")
        await page.click("#edit-submit")
        await asyncio.sleep(10)

        # Check result
        url = page.url
        title = await page.title()
        msg = await page.query_selector(".messages--status")
        msg_text = await msg.inner_text() if msg else "NO MESSAGE"
        print(f"URL: {url}")
        print(f"Title: {title}")
        print(f"Message: {msg_text}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
