"""Read-only authenticated JSON:API verification of RD 0304-0310.

Expected content comes from the reviewed JSON preview; PDF FIDs come from the
completed upload log. No browser navigation or portal writes are performed.
"""
import asyncio
import datetime
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode, urljoin

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "data/carga_drupal_preview.json"
UPLOAD_LOG = ROOT / "logs/carga_20261022_115353.log"
SUMMARY = ROOT / "logs/resumen_20261022_121037.json"
OUTPUT = ROOT / "logs/verificacion_0304_0310.json"
API = "https://www.ana.gob.pe/jsonapi/node/normatividad"
RDS = [f"{i:04d}" for i in range(304, 311)]
HEADERS = {"Accept": "application/vnd.api+json"}
FID_RE = re.compile(r"PDF subido vía .*?! Fids: (\d+)")


def normalized(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))).strip()


def target_id(data):
    if not isinstance(data, dict):
        return None
    return (data.get("meta") or {}).get("drupal_internal__target_id")


def load_expected():
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("total") != 7 or summary.get("completadas") != 7 or summary.get("fallidas") != [] or not summary.get("finalizado"):
        raise ValueError("Upload bot has no successful terminal summary; do not query a live upload")
    rows = json.loads(PREVIEW.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != 7:
        raise ValueError("Preview must contain exactly seven entries")
    expected = {}
    for row in rows:
        fields = row["fields"]
        title = fields["titulo"]
        match = re.fullmatch(r"RD N° (03\d\d)-2026-ANA-AAA\.MDD", title)
        if not match or match.group(1) not in RDS or match.group(1) in expected:
            raise ValueError("Unexpected or duplicate preview title")
        rd = match.group(1)
        attachments = row.get("adjuntos") or []
        if len(attachments) != len(row.get("adjuntos_rutas") or []):
            raise ValueError(f"RD {rd}: attachment name/path mismatch")
        if not normalized(fields.get("resumen")) or not fields.get("fecha_rd") or not fields.get("numero_resolucion"):
            raise ValueError(f"RD {rd}: missing expected field")
        if not row.get("archivo_pdf") or Path(fields.get("ruta_pdf", "")).name != row["archivo_pdf"]:
            raise ValueError(f"RD {rd}: PDF path/filename mismatch")
        expected[rd] = row
    if set(expected) != set(RDS):
        raise ValueError("Preview does not contain RD 0304-0310 exactly once")

    # Bind every upload FID to the preview's *exact* PDF names, in upload order.
    log = UPLOAD_LOG.read_text(encoding="utf-8")
    blocks = re.findall(r"RD \d/7: ([^\r\n]+\.pdf)(.*?)(?=RD \d/7: |\Z)", log, re.S)
    if len(blocks) != 7:
        raise ValueError("Upload log does not contain exactly seven RD blocks")
    fids = {}
    for name, block in blocks:
        found = [int(value) for value in FID_RE.findall(block)]
        if name in fids or len(found) < 1:
            raise ValueError("Missing or ambiguous FID list in upload log")
        fids[name] = found
    if set(fids) != {row["archivo_pdf"] for row in rows}:
        raise ValueError("Upload PDF names do not correspond to the preview")
    for row in rows:
        expected_count = 1 + len(row.get("adjuntos") or [])
        if len(fids[row["archivo_pdf"]]) != expected_count:
            raise ValueError(f"{row['archivo_pdf']}: FID count does not match attachments")
    flat = [fid for values in fids.values() for fid in values]
    if len(flat) != len(set(flat)):
        raise ValueError("Duplicate FIDs in upload log")
    return expected, fids


async def get_json(page, url):
    last_error = "no response"
    for attempt in range(3):
        try:
            response = await page.request.get(url, headers=HEADERS, timeout=30000)
            if response.status == 200:
                data = await response.json()
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    return data
                last_error = "invalid JSON:API response"
            else:
                last_error = f"HTTP {response.status}"
                if response.status in (401, 403):
                    break
        except Exception as exc:
            last_error = type(exc).__name__  # Never print private server responses.
        if attempt < 2:
            await asyncio.sleep(3)
    raise RuntimeError(last_error)


async def verify_one(page, rd, row, expected_fids):
    fields = row["fields"]
    title = fields["titulo"]
    url = API + "?" + urlencode({"filter[title][operator]": "CONTAINS", "filter[title][value]": title, "page[limit]": 50})
    nodes = []
    for _ in range(5):
        payload = await get_json(page, url)
        nodes.extend(n for n in payload["data"] if (n.get("attributes") or {}).get("title") == title)
        next_url = (payload.get("links") or {}).get("next")
        if isinstance(next_url, dict):
            next_url = next_url.get("href")
        if not next_url:
            break
        url = urljoin(API, next_url)
    else:
        raise RuntimeError("search pagination exceeds five pages")
    if len(nodes) != 1:
        return {"rd": rd, "status": "FAIL", "failed_checks": ["exact_unique_title"], "matching_nodes": len(nodes)}
    node = nodes[0]
    attrs = node.get("attributes") or {}
    relationships = node.get("relationships") or {}
    files = (relationships.get("field_file") or {}).get("data")
    file_ids = [target_id(file) for file in files] if isinstance(files, list) else []
    # Confirmed JSON:API keys: do not accept matching content from other fields.
    body = attrs.get("body")
    actual_summary = normalized(body.get("value") or body.get("processed")) if isinstance(body, dict) else ""
    date = attrs.get("field_fecha_de_aprobacion_de_la_")
    number = attrs.get("field_num_resolucion_mat")
    checks = {
        "exact_unique_title": True,
        "published": attrs.get("status") is True or attrs.get("status") == 1,
        "date": isinstance(date, str) and date[:10] == fields["fecha_rd"][:10] and (len(date) == 10 or date[10] in "T "),
        "number": str(number).strip() == str(fields["numero_resolucion"]).strip(),
        "full_summary": bool(actual_summary) and actual_summary == normalized(fields["resumen"]),
        "taxonomy_129": target_id((relationships.get("field_tipo_de_norma") or {}).get("data")) == 129,
        "administrative_17": target_id((relationships.get("field_administrativo") or {}).get("data")) == 17,
        "pdf_fids": file_ids == expected_fids,
    }
    result = {"rd": rd, "status": "OK" if all(checks.values()) else "FAIL",
              "failed_checks": [key for key, ok in checks.items() if not ok],
              "node_id": node.get("id"), "expected_fids": expected_fids,
              "portal_fids": file_ids, "summary_length": len(actual_summary)}
    missing = [key for key in ("body", "field_num_resolucion_mat") if key not in attrs]
    if missing:
        result["missing_canonical_fields"] = missing
        result["attribute_keys"] = sorted(attrs)
    return result


async def main():
    try:
        expected, fids = load_expected()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Preflight failed: {type(exc).__name__}: {exc}")
        return 1
    results = []
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(ROOT / "data/browser_profile"), headless=False,
                viewport={"width": 1920, "height": 1080}, locale="es-PE")
            try:
                page = await context.new_page()
                for rd in RDS:
                    row = expected[rd]
                    try:
                        result = await verify_one(page, rd, row, fids[row["archivo_pdf"]])
                    except Exception as exc:
                        result = {"rd": rd, "status": "FAIL", "failed_checks": ["api_or_auth"],
                                  "error_type": type(exc).__name__}
                    results.append(result)
                    print(f"RD {rd}: {result['status']} ({', '.join(result['failed_checks']) or 'all checks passed'})")
            finally:
                await context.close()
    except Exception as exc:
        print(f"Authentication/browser unavailable: {type(exc).__name__}")
        results.extend({"rd": rd, "status": "FAIL", "failed_checks": ["api_or_auth"]}
                       for rd in RDS[len(results):])
    ok = sum(r["status"] == "OK" for r in results)
    OUTPUT.write_text(json.dumps({"batch": "0304-0310", "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
                                  "expected_source": "data/carga_drupal_preview.json",
                                  "fid_source": "logs/carga_20261022_115353.log", "total": 7,
                                  "ok": ok, "fail": 7 - ok, "results": results},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Total: 7 | OK: {ok} | FAIL: {7 - ok}; evidence: logs/verificacion_0304_0310.json")
    return 0 if ok == 7 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
