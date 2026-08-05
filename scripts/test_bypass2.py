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

        # Bypass SHS with HTML5 validation-OK values
        await page.evaluate("""
            const tn = document.getElementById('edit-field-tipo-de-norma');
            tn.value = '129';
            tn.dispatchEvent(new Event('change', { bubbles: true }));
            tn.dispatchEvent(new Event('input', { bubbles: true }));
            
            const adm = document.getElementById('edit-field-administrativo');
            adm.value = '17';
            adm.dispatchEvent(new Event('change', { bubbles: true }));
            adm.dispatchEvent(new Event('input', { bubbles: true }));
        """)
        await asyncio.sleep(2)
        
        print("Hidden inputs:")
        tn = await page.evaluate("document.getElementById('edit-field-tipo-de-norma').value")
        adm = await page.evaluate("document.getElementById('edit-field-administrativo').value")
        print(f"  tipo-de-norma = '{tn}'")
        print(f"  administrativo = '{adm}'")

        # Also try setting the SHS select widget to match
        await page.evaluate("""
            // Set nivel 1 selects
            const tn1 = document.getElementById('edit-field-tipo-de-norma-shs-0-0');
            if (tn1) tn1.value = '115';
            const ad1 = document.getElementById('edit-field-administrativo-shs-0-0');
            if (ad1) ad1.value = '17';
        """)

        # Fill other required fields
        await page.fill("#edit-title-0-value", "TEST RD N 0206-2026-ANA-AAA.MDD")
        await page.fill("#edit-field-fecha-de-aprobacion-de-la-0-value-date", "2026-07-30")
        await page.fill("#edit-field-fecha-de-aprobacion-de-la-0-value-time", "08:00:00")
        await page.fill("#edit-field-num-resolucion-mat-0-value", "206")
        print("Fields filled")

        # Submit
        print("Submitting...")
        await page.click("#edit-submit")
        await asyncio.sleep(8)

        # Check page
        url = page.url
        print(f"\nURL: {url}")
        
        # Check all messages
        for cls in [".messages--error", ".messages--status", ".messages--warning"]:
            msgs = await page.query_selector_all(cls)
            for m in msgs:
                text = await m.inner_text()
                print(f"[{cls}] {text.strip()[:500]}")

        # Check for form errors (red highlights)
        errors = await page.query_selector_all(".form-item--error, .error, [aria-invalid='true']")
        print(f"\nForm errors found: {len(errors)}")
        for e in errors[:10]:
            label = await e.query_selector("label")
            label_text = await label.inner_text() if label else "no label"
            desc = await e.query_selector(".form-item--error-message, .description")
            desc_text = await desc.inner_text() if desc else "no desc"
            print(f"  - {label_text.strip()}: {desc_text.strip()[:200]}")

        await page.screenshot(path=str(ROOT / "logs" / "test_bypass2.png"), full_page=True)
        print("\nScreenshot: logs/test_bypass2.png")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
