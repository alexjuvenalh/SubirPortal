# Plan de Orquestador — Modo 1 (Semi-Automático)

> **IMPLEMENTADO** — 2026-05-26
> Script: `correr_todo.ps1` en la raíz del proyecto.

## Objetivo

Un solo comando PowerShell que ejecute todo el flujo de carga Drupal,
con una **pausa obligatoria para revisión manual del Excel**.

## Comando propuesto

```powershell
.\correr_todo.ps1
```

## Flujo

```
┌─────────────────────────────────────────────────────────┐
│ 1. generar_planilla.py                                   │
│    Escanea pdfs/nuevos/ → data/resoluciones_pendientes.xlsx │
├─────────────────────────────────────────────────────────┤
│ 2. Abre el Excel automáticamente (Start-Process)         │
│    ⏸️  PAUSA: El usuario revisa y corrige manualmente    │
│    El script espera a que cierre el Excel (Wait-Process) │
├─────────────────────────────────────────────────────────┤
│ 3. preparar_carga_drupal.py                              │
│    Lee el Excel → data/carga_drupal_preview.json         │
├─────────────────────────────────────────────────────────┤
│ 4. subir_a_drupal.py                                     │
│    Lee el JSON → abre Chromium → publica en Drupal       │
│    Si no hay sesión, pide login manual                   │
├─────────────────────────────────────────────────────────┤
│ 5. Mueve los PDFs publicados a pdfs/procesados/          │
└─────────────────────────────────────────────────────────┘
```

## Reglas

- **No se saltea la revisión del Excel** — publicar metadatos erróneos en una entidad pública no es aceptable.
- Si `subir_a_drupal.py` falla, los PDFs **no** se mueven a `procesados/`.
- Los logs y screenshots quedan en `logs/` para auditoría.

## Opcional futuro: flag `-Auto`

Para cuando se confíe 100% en los datos extraídos:

```powershell
.\correr_todo.ps1 -Auto   # Sin pausa de revisión
```

---

# Soporte Multi-AAA (futuro)

## Problema

ANA tiene 13 AAAs y 150+ ALAs a nivel nacional. El formulario Drupal es el mismo para todos, pero cada jurisdicción tiene:

- Distinto `value` en el select de Ámbito Administrativo
- Algunas AAA requieren seleccionar ALA en el segundo nivel (hoy va `_none`)
- Distintos prefijos de PDF → mapeo de ALA

## Solución propuesta

Archivos de configuración por jurisdicción:

```
config/
├── drupal_field_map.json        # Selectores (genérico, no cambia)
├── aaa_madre_de_dios.json       # Ámbito: 17, prefijos: 59/64
├── aaa_cusco.json               # Ámbito: XX, prefijos: YY/ZZ
└── aaa_...json                  # Una por cada AAA
```

Cada archivo contiene solo lo que varía:

```json
{
  "nombre": "AAA Madre de Dios",
  "ambito_administrativo_nivel_1": "17",
  "ambito_administrativo_nivel_2": "_none",
  "prefijos_ala": {
    "59": "ALA Tahuamanu Madre de Dios",
    "64": "ALA Tambopata - Inambari"
  }
}
```

Los scripts leerían la config por parámetro:

```powershell
.\correr_todo.ps1 -AAA "madre_de_dios"
```

---

# Stack Técnico del Bot

## Dependencias

| Paquete | Uso |
|---------|-----|
| **Playwright** (Python) | Automatización de navegador Chromium |
| **pypdf** | Extraer texto de PDFs |
| **openpyxl** | Leer/escribir Excel |

## No usa

- ❌ IA / LLM / APIs de OpenAI o Claude
- ❌ MCP (Model Context Protocol)
- ❌ Selenium
- ❌ APIs de ANA (no existen)
- ❌ Docker

## Técnicas clave

| Técnica | Problema que resolvió |
|---------|----------------------|
| `dispatchEvent('mousedown')` vía JS | Botón "Subir al servidor" oculto con `js-hide` |
| `wait_for_selector(state="attached")` | Opciones de select hidden durante AJAX |
| `launch_persistent_context` | Mantener cookies entre sesiones |
| Polling c/3s (`wait_for_selector`) | Esperar login manual sin `input()` |
| `frame_locator()` | Interactuar con CKEditor dentro del iframe |

## Perfil del navegador

- `data/browser_profile/` — cookies, localStorage, sesión Drupal.
- Se reutiliza entre ejecuciones para no pedir login cada vez.
- Si la sesión expira, el bot redirige a `/user/login` y espera.

---

# Estado actual del proyecto

| Script | Estado |
|--------|--------|
| `generar_planilla.py` | ✅ Funcional |
| `preparar_carga_drupal.py` | ✅ Funcional |
| `subir_a_drupal.py` | ✅ Funcional — 3 RDs publicadas |
| `correr_todo.ps1` (orquestador) | 🔲 Pendiente de construir |
| Configs multi-AAA | 🔲 Pendiente de diseñar |

## Última ejecución exitosa

- **Fecha**: 2026-05-25
- **RDs publicadas**: 3/3
  - `59-RD-0151-2026-04.pdf` → fids `659364`
  - `59-RD-0152-2026-04.pdf` → fids `659365`
  - `59-RD-0153-2026-03.pdf` → fids `659366`
- **PDFs movidos a**: `pdfs/procesados/`

---

# Glosario

| Término | Significado |
|---------|-------------|
| **Dry-run** | Ensayo completo sin ejecutar la acción final (Guardar) |
| **Playwright** | Librería de Microsoft para automatizar navegadores |
| **Chromium** | Motor open-source de Chrome, sin los servicios de Google |
| **fids** | File IDs — identificador que Drupal asigna a un archivo subido |
| **CKEditor** | Editor de texto enriquecido que Drupal usa para el campo Resumen |
| **managed_file** | Widget de Drupal para subir archivos con AJAX |
| **AAA** | Autoridad Administrativa del Agua (13 a nivel nacional) |
| **ALA** | Administración Local de Agua (150+ a nivel nacional) |
