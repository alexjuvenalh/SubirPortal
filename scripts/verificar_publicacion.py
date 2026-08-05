"""Verifica en el portal que las 4 RDs estén publicadas con sus archivos y taxonomía.

Usa el browser con sesión para consultar JSON:API autenticado:
- Busca cada título de RD
- Verifica field_file (PDF + planos), field_tipo_de_norma (129), field_administrativo (17)
"""
import asyncio, json, sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

from playwright.async_api import async_playwright

TITULOS = [
    "RD N° 0209-2026-ANA-AAA.MDD",
    "RD N° 0210-2026-ANA-AAA.MDD",
    "RD N° 0211-2026-ANA-AAA.MDD",
    "RD N° 0212-2026-ANA-AAA.MDD",
]


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        for titulo in TITULOS:
            numero = titulo.split("N° ")[1].split("-2026")[0]
            print(f"\n=== {titulo} ===")
            encoded = titulo.replace(" ", "%20")
            url = (f"https://www.ana.gob.pe/jsonapi/node/normatividad"
                   f"?filter[title][operator]=CONTAINS&filter[title][value]={encoded}"
                   f"&fields[node--normatividad]=title,field_file,field_tipo_de_norma,field_administrativo"
                   f"&include=field_file,field_tipo_de_norma,field_administrativo"
                   f"&page[limit]=5")
            try:
                resp = await page.request.get(url, headers={"Accept": "application/vnd.api+json"})
                data = await resp.json()
            except Exception as e:
                print(f"  ❌ Error consultando API: {e}")
                continue

            nodos = data.get("data", [])
            if not nodos:
                print(f"  ❌ NO encontrado en JSON:API")
                continue

            # Buscar el nodo exacto (CONTAINS puede traer otros)
            exacto = [n for n in nodos if n.get("attributes", {}).get("title") == titulo]
            if not exacto:
                print(f"  ⚠️  Solo parcial: {[n['attributes'].get('title') for n in nodos]}")
                continue

            n = exacto[0]
            attrs = n["attributes"]
            rel = n.get("relationships", {})

            # field_file
            ff = rel.get("field_file", {}).get("data") or []
            archivos = [a["meta"].get("alt", "?") for a in ff] if isinstance(ff, list) else []
            print(f"  ✅ Encontrado: {attrs.get('title')}")
            print(f"  📄 field_file: {len(archivos)} archivo(s)")

            # field_tipo_de_norma
            ftn = rel.get("field_tipo_de_norma", {}).get("data")
            print(f"  🏷️  tipo_de_norma: {ftn}")
            # field_administrativo
            fa = rel.get("field_administrativo", {}).get("data")
            print(f"  🗺️  administrativo: {fa}")

        await context.close()
        print("\n✅ Verificación completada.")


if __name__ == "__main__":
    asyncio.run(main())
