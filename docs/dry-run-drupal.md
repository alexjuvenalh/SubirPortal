# Dry-run Drupal — 2026-05-25

Se probó llenar la primera fila de `data/carga_drupal_preview.json` en:

```text
https://www.ana.gob.pe/node/add/normatividad
```

No se presionó `Guardar`.

## Resultado verificado

Para `59-RD-0151-2026-04.pdf`:

- Título: `RD N° 0151-2026-ANA-AAA.MDD`
- Fecha: `2026-05-21`
- Hora: `08:00:00`
- Número obligatorio: `151`
- Clasificación nivel 1: `Resoluciones Emitidas por la ANA`
- Clasificación nivel 2: `De las Autoridades Administrativas del Agua`
- Hidden clasificación: `129`
- Ámbito nivel 1: `AAA Madre de Dios`
- Ámbito nivel 2: `- None -`
- Hidden ámbito: `17`
- Resumen: cargado correctamente en el editor CKEditor visible.
- Archivo PDF: subido correctamente con `field_file[0][fids]`.

## Campos que NO debe tocar el bot

- `Información para TNCRH`
- `CUT`
- `Autor`
- `Titulo_Corto`
- `Año`
- Número de resolución opcional inferior
- Materia
- Solicitante
- Administrado
- Sumilla
- Etiquetas
- Gestionamos a través de
- Destacar en Accesos Directos

## Hallazgos técnicos

- Los selects jerárquicos de clasificación y ámbito administrativo se reconstruyen por AJAX.
- El bot debe esperar a que exista la opción deseada antes de seleccionar el segundo nivel.
- El campo `Resumen` usa CKEditor: el `textarea` real existe pero está oculto.
- Para cargar `Resumen`, hay que escribir en:

  ```text
  iframe[title="Editor de texto con formato, campo Resumen"] body
  ```

- Después de subir un archivo, Drupal crea una fila administrada con `field_file[0][fids]` y un link al PDF. También crea un nuevo input vacío para subir otro archivo; ese input vacío NO significa que la carga anterior falló.
