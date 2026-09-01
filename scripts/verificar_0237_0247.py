"""Verifica en el portal que las RDs 0237-0247 estén publicadas con sus archivos y taxonomía.

Usa el browser con sesión para consultar JSON:API autenticado:
- Busca cada título de RD
- Verifica field_file, field_tipo_de_norma (129), field_administrativo (17) y fecha
"""
import asyncio, json, sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

from playwright.async_api import async_playwright

TITULOS = [
    "RD N° 0237-2026-ANA-AAA.MDD",
    "RD N° 0238-2026-ANA-AAA.MDD",
    "RD N° 0239-2026-ANA-AAA.MDD",
    "RD N° 0240-2026-ANA-AAA.MDD",
    "RD N° 0241-2026-ANA-AAA.MDD",
    "RD N° 0242-2026-ANA-AAA.MDD",
    "RD N° 0243-2026-ANA-AAA.MDD",
    "RD N° 0244-2026-ANA-AAA.MDD",
    "RD N° 0245-2026-ANA-AAA.MDD",
    "RD N° 0246-2026-ANA-AAA.MDD",
    "RD N° 0247-2026-ANA-AAA.MDD",
]


def _target_id(rel_data):
    """Extrae el drupal_internal__target_id de un relationship data (objeto o lista)."""
    if isinstance(rel_data, list):
        return [_target_id(x) for x in rel_data]
    if isinstance(rel_data, dict):
        meta = rel_data.get("meta") or {}
        return meta.get("drupal_internal__target_id")
    return None


async def main():
    user_data_dir = ROOT / "data" / "browser_profile"
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        resultados = []
        for titulo in TITULOS:
            numero = titulo.split("N° ")[1].split("-2026")[0]
            print(f"\n=== {titulo} ===")
            encoded = titulo.replace(" ", "%20")
            url = (f"https://www.ana.gob.pe/jsonapi/node/normatividad"
                   f"?filter[title][operator]=CONTAINS&filter[title][value]={encoded}"
                   f"&fields[node--normatividad]=title,field_fecha_de_aprobacion_de_la_,field_file,field_tipo_de_norma,field_administrativo"
                   f"&include=field_file,field_tipo_de_norma,field_administrativo"
                   f"&page[limit]=5")
            try:
                resp = await page.request.get(url, headers={"Accept": "application/vnd.api+json"})
                data = await resp.json()
            except Exception as e:
                print(f"  ❌ Error consultando API: {e}")
                resultados.append({"rd": numero, "status": "ERROR_API", "detalle": str(e)})
                continue

            nodos = data.get("data", [])
            if not nodos:
                print(f"  ❌ NO encontrado en JSON:API")
                resultados.append({"rd": numero, "status": "NO_ENCONTRADO"})
                continue

            exacto = [n for n in nodos if n.get("attributes", {}).get("title") == titulo]
            if not exacto:
                print(f"  ⚠️  Solo parcial: {[n['attributes'].get('title') for n in nodos]}")
                resultados.append({"rd": numero, "status": "PARCIAL", "detalle": [n['attributes'].get('title') for n in nodos]})
                continue

            n = exacto[0]
            attrs = n["attributes"]
            rel = n.get("relationships", {})

            fecha = attrs.get("field_fecha_de_aprobacion_de_la_")
            ff = rel.get("field_file", {}).get("data") or []
            n_archivos = len(ff) if isinstance(ff, list) else 0
            ftn = _target_id(rel.get("field_tipo_de_norma", {}).get("data"))
            adm = _target_id(rel.get("field_administrativo", {}).get("data"))

            print(f"  ✅ Encontrado: {attrs.get('title')}")
            print(f"  📅 fecha de aprobación: {fecha}")
            print(f"  📄 field_file: {n_archivos} archivo(s)")
            print(f"  🏷️  tipo_de_norma: {ftn} (esperado 129)")
            print(f"  🗺️  administrativo: {adm} (esperado 17)")

            ok = (n_archivos >= 1 and ftn == 129 and adm == 17)
            resultados.append({
                "rd": numero,
                "status": "OK" if ok else "REVISAR",
                "fecha": fecha,
                "archivos": n_archivos,
                "tipo_de_norma": ftn,
                "administrativo": adm,
            })

        await context.close()
        print("\n\n======== RESUMEN VERIFICACION ========")
        for r in resultados:
            print(f"  RD {r['rd']}: {r['status']}")

        # Guardar resumen
        out = ROOT / "logs" / f"verificacion_0237_0247_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nResumen guardado: {out}")


if __name__ == "__main__":
    asyncio.run(main())