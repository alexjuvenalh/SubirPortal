"""Fetch SHS term data for classification and ambito fields."""
import urllib.request
import json

# Classification children
url = "https://www.ana.gob.pe/shs-term-data/shs-field-tipo-de-norma/tipo_de_norma/115"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode("utf-8"))

print("=== Clasificacion: children of 115 (Resoluciones Emitidas por la ANA) ===")
for item in data:
    print(f"  tid={item['tid']}  hasChildren={item.get('hasChildren', False)}  name={item['name']}")

# Ambito children
url2 = "https://www.ana.gob.pe/shs-term-data/shs-field-administrativo/organos_desconcentrados/17"
req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
resp2 = urllib.request.urlopen(req2)
data2 = json.loads(resp2.read().decode("utf-8"))

print("\n=== Ambito: children of 17 (AAA Madre de Dios) ===")
for item in data2:
    print(f"  tid={item['tid']}  hasChildren={item.get('hasChildren', False)}  name={item['name']}")

# Also fetch ambito root to confirm structure
url3 = "https://www.ana.gob.pe/shs-term-data/shs-field-administrativo/organos_desconcentrados/0"
req3 = urllib.request.Request(url3, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
resp3 = urllib.request.urlopen(req3)
data3 = json.loads(resp3.read().decode("utf-8"))

print("\n=== Ambito: root ===")
for item in data3:
    print(f"  tid={item['tid']}  hasChildren={item.get('hasChildren', False)}  name={item['name']}")
