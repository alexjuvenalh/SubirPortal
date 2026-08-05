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

        # Wait for SHS to initialize
        await asyncio.sleep(3)

        # Try to directly call SHS internal API
        result = await page.evaluate("""
            () => {
                // Find the SHS widget model
                const container = document.querySelector(
                    '#edit-field-tipo-de-norma-wrapper .shs-container');
                if (!container) return 'No SHS container found';
                
                // Drupal attaches behaviors data
                const drupalSettings = window.drupalSettings || {};
                
                // Check if shs settings exist
                const shsSettings = drupalSettings.shs || {};
                const fieldSettings = shsSettings['field-tipo-de-norma'] || {};
                
                let info = {
                    hasDrupalSettings: !!drupalSettings,
                    shsKeys: Object.keys(drupalSettings.shs || {}),
                    fieldSettingsKeys: Object.keys(fieldSettings),
                    fieldSettings: JSON.stringify(fieldSettings).substring(0, 1000)
                };
                
                // Check Drupal.SHS if available
                if (typeof Drupal !== 'undefined' && Drupal.SHS) {
                    info.hasDrupalSHS = true;
                    info.shsMethods = Object.keys(Drupal.SHS);
                }
                
                // Try to access the Backbone/Drupal model
                if (typeof Drupal !== 'undefined') {
                    const ajaxSettings = drupalSettings.ajax || {};
                    info.ajaxKeys = Object.keys(ajaxSettings).slice(0, 20);
                }
                
                return JSON.stringify(info, null, 2);
            }
        """)
        print("SHS internal state:")
        print(result)

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
