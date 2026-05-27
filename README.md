# Automatización de Resoluciones Directorales ANA

Proyecto para preparar y luego automatizar la carga de Resoluciones Directorales al portal institucional de ANA.

## Orquestador (un solo comando)

El script `correr_todo.ps1` ejecuta el flujo completo con una pausa obligatoria para revisar el Excel:

```powershell
.\correr_todo.ps1
```

### Qué hace

| Paso | Acción |
|---|---|
| 0 | Verifica que haya PDFs en `pdfs/nuevos/` |
| 1 | `generar_planilla.py` — extrae metadata de PDFs a Excel |
| 2 | Abre el Excel y **pausa** para revisión manual |
| 3 | `preparar_carga_drupal.py` — convierte Excel a JSON + detecta adjuntos |
| 4 | Confirmación — pregunta SI/NO antes de publicar |
| 5 | `subir_a_drupal.py` — bot Playwright publica en Drupal |
| 6 | Mueve los PDFs a `pdfs/procesados/` |

### Opciones

```powershell
# Modo automático (sin pausa de revisión)
.\correr_todo.ps1 -Auto

# Especificar Python manualmente
.\correr_todo.ps1 -PythonPath "C:\Python311\python.exe"
```

### Requisitos

- PowerShell 5.1 (viene con Windows 10/11)
- Python con Playwright instalado
- Política de ejecución: si PowerShell bloquea el script, ejecutar:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\correr_todo.ps1
```

### Cómo usarlo

1. Colocá los PDFs (principales + planos + anexos) en `pdfs/nuevos/`
2. Ejecutá `.\correr_todo.ps1`
3. Cuando se abra el Excel, **revisá los datos** (título, fecha, número, resumen)
4. Guardá los cambios en el Excel, volvé a la terminal y presioná ENTER
5. Confirmá la publicación con `SI`
6. El bot abre Chromium, publica todo, y mueve los PDFs a `procesados/`

---

## Flujo manual (scripts individuales)

Si preferís ejecutar paso a paso:

1. Colocar los PDFs firmados en:

   ```text
   pdfs/nuevos/
   ```

2. Generar la planilla de revisión:

   ```powershell
   & "C:\Users\Alex H\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\scripts\generar_planilla.py
   ```

3. Revisar el archivo generado:

   ```text
   data/resoluciones_pendientes.xlsx
   ```

4. Corregir manualmente cualquier dato dudoso antes de automatizar la carga al portal.

## Campos preparados para Drupal

- `titulo_sugerido`: formato `RD N° 0151-2026-ANA-AAA.MDD`.
- `numero_resolucion`: número sin ceros iniciales, por ejemplo `151`.
- `fecha_rd`: fecha de la resolución.
- `hora_rd`: `08:00:00 am` por defecto.
- `clasificacion_1`: `Resoluciones Emitidas por el ANA`.
- `clasificacion_2`: `De las Autoridades Administrativas del Agua`.
- `ambito_administrativo`: `AAA Madre de Dios`.
- `resumen_portal`: texto que el bot cargará en el campo `Resumen`; por defecto usa `articulo_1` y se puede editar manualmente.
- `articulo_1`, `articulo_2`, `articulo_3`: primeros artículos extraídos de la parte resolutiva para elegir cuál usar como resumen.

## Reglas de negocio conocidas

- PDFs/RDs que comienzan con `59` → `ALA Tahuamanu Madre de Dios`.
- PDFs/RDs que comienzan con `64` → `ALA Tambopata - Inambari`.

## Criterio de seguridad

La automatización debe pasar por una planilla de revisión antes de publicar en Drupal. En una entidad pública, publicar metadatos erróneos no es un detalle menor: primero se valida, después se carga.

## Mapeo Drupal

El mapeo técnico inicial del formulario Drupal está en:

```text
config/drupal_field_map.json
```

Ese archivo guarda los selectores HTML y valores verificados para los campos activos: título, fecha, hora, número de resolución, clasificación, resumen, archivo PDF y ámbito administrativo.

Hallazgos del primer dry-run:

```text
docs/dry-run-drupal.md
```

Regla actual del bot:

- No tocar `Información para TNCRH`.
- No tocar `Autor`.
- No tocar `Titulo_Corto`.
- En `Ámbito Administrativo`, seleccionar `AAA Madre de Dios` en el primer select y dejar `- None -` en el segundo.
- Enfocar la siguiente etapa en carga de PDF en `Archivo`.

## Preparar preview de carga Drupal

Después de revisar el Excel, generar el JSON de carga:

```powershell
& "C:\Users\Alex H\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\scripts\preparar_carga_drupal.py
```

Salida:

```text
data/carga_drupal_preview.json
```

Este archivo sirve para verificar exactamente qué datos intentará cargar el bot antes de tocar Drupal.

## Bot de carga automática a Drupal

Una vez validado el preview, ejecutar el bot que llena el formulario, sube los PDFs y publica:

```powershell
& "C:\Users\Alex H\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" .\scripts\subir_a_drupal.py
```

### Requisitos previos

- Playwright instalado (`pip install playwright && playwright install chromium`)
- El bot usa un perfil persistente en `data/browser_profile/` para mantener cookies.
- En el primer uso, el bot detecta que no hay sesión, redirige a `/user/login` y espera a que inicies sesión manualmente. Después navegá a `/node/add/normatividad` y el bot continúa automáticamente.

### Qué hace el bot

1. Navega al formulario `/node/add/normatividad`
2. Para cada RD en `carga_drupal_preview.json`:
   - Llena título, fecha, hora, número de resolución
   - Selecciona clasificación (2 niveles con AJAX)
   - Selecciona ámbito administrativo (AAA Madre de Dios)
   - Llena el resumen vía CKEditor
   - Sube el PDF (dispara el AJAX de Drupal para el managed_file)
   - Presiona **Guardar**
3. Genera screenshots en `logs/screenshots/` para auditoría
4. Muestra resumen final con totales

### Hallazgos técnicos del bot

- El botón "Subir al servidor" del widget managed_file está oculto con clase `js-hide` porque Drupal usa `auto-file-upload`. Playwright no dispara el evento nativo completo, por lo que se fuerza con `dispatchEvent(new MouseEvent('mousedown'))` sobre el botón para activar el AJAX de Drupal.
- Los selects en cascada usan `state="attached"` en vez de `state="visible"` porque las opciones existen en el DOM pero Drupal las mantiene hidden durante la transición AJAX.
