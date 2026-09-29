"""Verifica en el portal que las RDs 0268-0272 estén publicadas con archivo, taxonomía y resumen.

Mismo patrón que verificar_0254_0267.py: browser con sesión persistente contra
JSON:API autenticado de Drupal (el portal exige sesión para leer el nodo completo).

Checks por RD:
  - título exacto (evita falsos positivos del filtro CONTAINS)
  - field_file: >= 1 archivo y el fid coincide con el esperado en el log de carga
  - field_tipo_de_norma: target_id == 129  (SHS nivel 2, inyectado manualmente este lote)
  - field_administrativo: target_id == 17
  - field_fecha_de_aprobacion_de_la_: coincide con la fecha esperada del preview
  - body (resumen): prefijo normalizado coincide con data/carga_drupal_preview.json
"""
import asyncio
import datetime
import html
import json
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "data" / "carga_drupal_preview.json"

from playwright.async_api import async_playwright

TITULOS = [
    "RD N° 0268-2026-ANA-AAA.MDD",
    "RD N° 0269-2026-ANA-AAA.MDD",
    "RD N° 0270-2026-ANA-AAA.MDD",
    "RD N° 0271-2026-ANA-AAA.MDD",
    "RD N° 0272-2026-ANA-AAA.MDD",
]

FECHAS_ESPERADAS = {
    "0268": "2026-09-21",
    "0269": "2026-09-22",
    "0270": "2026-09-22",
    "0271": "2026-09-28",
    "0272": "2026-09-28",
}

# Fids reportados por el bot en logs/carga_20260929_121348.log
FIDS_ESPERADOS = {
    "0268": 684084,
    "0269": 684087,
    "0270": 684089,
    "0271": 684091,
    "0272": 684093,
}

API = "https://www.ana.gob.pe/jsonapi/node/normatividad"
CAMPOS = ("title,field_fecha_de_aprobacion_de_la_,field_file,"
          "field_tipo_de_norma,field_administrativo")


def cargar_preview():
    """Devuelve {numero_rd: {titulo, fecha, numero, resumen}} desde el preview."""
    salida = {}
    if not PREVIEW.exists():
        return salida
    for item in json.loads(PREVIEW.read_text(encoding="utf-8")):
        f = item.get("fields", {})
        titulo = f.get("titulo", "")
        if "N° " not in titulo:
            continue
        numero = titulo.split("N° ")[1].split("-2026")[0]
        salida[numero] = {
            "titulo": titulo,
            "fecha": f.get("fecha_rd", ""),
            "numero": f.get("numero_resolucion", ""),
            "resumen": f.get("resumen", ""),
            "pdf": item.get("archivo_pdf", ""),
        }
    return salida


def _target_id(rel_data):
    """Extrae el drupal_internal__target_id de un relationship data (objeto o lista)."""
    if isinstance(rel_data, list):
        return [_target_id(x) for x in rel_data]
    if isinstance(rel_data, dict):
        meta = rel_data.get("meta") or {}
        return meta.get("drupal_internal__target_id")
    return None


def normalizar(texto):
    """Quita HTML, entidades y espacios sobrantes para comparar resúmenes."""
    if not texto:
        return ""
    limpio = re.sub(r"<[^>]+>", " ", str(texto))
    limpio = html.unescape(limpio)
    return re.sub(r"\s+", " ", limpio).strip()


async def descubrir_campo_body(page, titulo):
    """Arma el sparse fieldset real: el nombre interno del campo Resumen no está
    en config/drupal_field_map.json, así que se descubre con una request sin
    filtro de fields (Drupal devuelve todos los atributos)."""
    url = (f"{API}?filter[title][operator]=CONTAINS&filter[title][value]={titulo}"
           f"&page[limit]=1")
    try:
        resp = await page.request.get(url, headers={"Accept": "application/vnd.api+json"})
        data = await resp.json()
    except Exception:
        return None
    for n in data.get("data", []):
        for key, valor in (n.get("attributes") or {}).items():
            if not isinstance(valor, dict) or "processed" not in valor:
                continue
            if len(str(valor.get("value", ""))) > 40:
                return key
    return None


async def main():
    preview = cargar_preview()
    user_data_dir = ROOT / "data" / "browser_profile"
    resultados = []

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir), headless=False,
            viewport={"width": 1920, "height": 1080}, locale="es-PE")
        page = await context.new_page()

        campo_body = await descubrir_campo_body(page, TITULOS[0].replace(" ", "%20"))
        print(f"Campo de resumen detectado: {campo_body}")
        campos = CAMPOS if not campo_body else f"{CAMPOS},{campo_body}"

        for titulo in TITULOS:
            numero = titulo.split("N° ")[1].split("-2026")[0]
            esperado = preview.get(numero, {})
            print(f"\n=== {titulo} ===")
            encoded = titulo.replace(" ", "%20")
            url = (f"{API}?filter[title][operator]=CONTAINS&filter[title][value]={encoded}"
                   f"&fields[node--normatividad]={campos}"
                   f"&include=field_file,field_tipo_de_norma,field_administrativo"
                   f"&page[limit]=5")
            try:
                resp = await page.request.get(url, headers={"Accept": "application/vnd.api+json"})
                data = await resp.json()
            except Exception as e:
                print(f"  ERROR consultando API: {e}")
                resultados.append({"rd": numero, "status": "ERROR_API", "detalle": str(e)})
                continue

            nodos = data.get("data", [])
            if not nodos:
                print("  NO encontrado en JSON:API")
                resultados.append({"rd": numero, "status": "NO_ENCONTRADO"})
                continue

            exacto = [n for n in nodos if (n.get("attributes") or {}).get("title") == titulo]
            if not exacto:
                print(f"  Solo parcial: {[n['attributes'].get('title') for n in nodos]}")
                resultados.append({"rd": numero, "status": "PARCIAL",
                                   "detalle": [n["attributes"].get("title") for n in nodos]})
                continue

            n = exacto[0]
            attrs = n.get("attributes") or {}
            rel = n.get("relationships") or {}

            fecha = attrs.get("field_fecha_de_aprobacion_de_la_")
            ff = rel.get("field_file", {}).get("data") or []
            fids = _target_id(ff) or []
            ftn = _target_id(rel.get("field_tipo_de_norma", {}).get("data"))
            adm = _target_id(rel.get("field_administrativo", {}).get("data"))
            resumen_esp = normalizar(esperado.get("resumen", ""))
            resumen_real = normalizar(attrs.get(campo_body, {}).get("processed", "")) if campo_body else ""

            fecha_esp = FECHAS_ESPERADAS.get(numero, "")
            fid_esp = FIDS_ESPERADOS.get(numero)

            fecha_ok = bool(fecha) and fecha_esp in str(fecha)
            archivos_ok = len(fids) >= 1
            fid_ok = (fid_esp is None) or (fid_esp in fids)
            tipo_ok = ftn == 129
            adm_ok = adm == 17
            resumen_ok = bool(resumen_esp) and resumen_real[:60] == resumen_esp[:60]

            print(f"  fecha:      {fecha} (esperado {fecha_esp}) -> {'OK' if fecha_ok else 'FAIL'}")
            print(f"  archivos:   {fids} (esperado fid {fid_esp}) -> {'OK' if archivos_ok and fid_ok else 'FAIL'}")
            print(f"  tipo_norma: {ftn} (esperado 129) -> {'OK' if tipo_ok else 'FAIL'}")
            print(f"  admin:      {adm} (esperado 17) -> {'OK' if adm_ok else 'FAIL'}")
            print(f"  resumen:    {len(resumen_real)} chars vs {len(resumen_esp)} esperados"
                  f" -> {'OK' if resumen_ok else 'FAIL'}")

            checks = {
                "fecha": fecha_ok,
                "archivos": archivos_ok and fid_ok,
                "tipo_de_norma": tipo_ok,
                "administrativo": adm_ok,
                "resumen": resumen_ok,
            }
            fallan = [k for k, v in checks.items() if not v]
            resultados.append({
                "rd": numero,
                "status": "OK" if not fallan else "FAIL",
                "campos_fallidos": fallan,
                "fecha": fecha,
                "fecha_esperada": fecha_esp,
                "archivos": len(fids),
                "fids": fids,
                "fid_esperado": fid_esp,
                "tipo_de_norma": ftn,
                "administrativo": adm,
                "resumen_chars": len(resumen_real),
                "resumen_esperado_chars": len(resumen_esp),
            })

        await context.close()

    ok = [r for r in resultados if r["status"] == "OK"]
    print("\n\n======== RESUMEN VERIFICACION 0268-0272 ========")
    print(f"  {'RD':<6} {'ESTADO':<8} {'FECHA':<12} {'FIDS':<10} {'TIPO':<6} {'ADMIN':<6} RESUMEN")
    for r in resultados:
        print(f"  {r['rd']:<6} {r['status']:<8} {str(r.get('fecha', '-'))[:10]:<12} "
              f"{str(r.get('fids', '-')):<10} {str(r.get('tipo_de_norma', '-')):<6} "
              f"{str(r.get('administrativo', '-')):<6} {r.get('resumen_chars', '-')}")
    print(f"\n  Total: {len(resultados)} | OK: {len(ok)} | FAIL: {len(resultados) - len(ok)}")

    out = ROOT / "logs" / f"verificacion_0268_0272_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResumen guardado: {out}")
    return 0 if len(ok) == len(resultados) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
