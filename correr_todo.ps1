<#
.SYNOPSIS
    Orquestador semi-automático para publicar Resoluciones Directorales en Drupal ANA.

.DESCRIPTION
    Ejecuta el flujo completo: genera planilla Excel, pausa para revisión manual,
    prepara carga Drupal, publica con bot Playwright, y mueve PDFs a procesados.

    La pausa en el Excel es OBLIGATORIA -- publicar metadatos erroneos en una
    entidad publica no es aceptable.

.PARAMETER Auto
    Omite la pausa de revision del Excel. Usar SOLO cuando se confie 100% en
    los datos extraidos automaticamente.

.PARAMETER PythonPath
    Ruta al ejecutable de Python. Por defecto usa el runtime de Codex.

.EXAMPLE
    .\correr_todo.ps1
    Ejecuta el flujo completo con pausa para revisar el Excel.

.EXAMPLE
    .\correr_todo.ps1 -Auto
    Ejecuta sin pausa de revision (solo para datos ya validados).

.EXAMPLE
    .\correr_todo.ps1 -PythonPath "C:\Python311\python.exe"
    Usa una instalacion especifica de Python.

.NOTES
    Requiere PowerShell 5.1 o superior.
    No modifica politicas de ejecucion del sistema.
#>

[CmdletBinding()]
param(
    [switch] $Auto,
    [string] $PythonPath = ""
)

# ============================================================
# CONFIGURACION
# ============================================================
$ErrorActionPreference = "Stop"
$script:Root = $PSScriptRoot
$script:PdfsNuevos = Join-Path $Root "pdfs\nuevos"
$script:PdfsProcesados = Join-Path $Root "pdfs\procesados"
$script:ExcelOutput = Join-Path $Root "data\resoluciones_pendientes.xlsx"
$script:JsonPreview = Join-Path $Root "data\carga_drupal_preview.json"

# Detectar Python
if (-not $PythonPath) {
    $codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexPython) {
        $PythonPath = $codexPython
    } else {
        # Fallback: buscar python en PATH
        $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
    Write-Host "[ERROR] No se encontro Python." -ForegroundColor Red
    Write-Host "Especifica la ruta con: .\correr_todo.ps1 -PythonPath 'C:\...\python.exe'" -ForegroundColor Yellow
    exit 1
}

# ============================================================
# FUNCIONES
# ============================================================

function Write-Step {
    param([string] $Text, [string] $Color = "Cyan")
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor $Color
    Write-Host "  $Text" -ForegroundColor $Color
    Write-Host ("=" * 60) -ForegroundColor $Color
    Write-Host ""
}

function Write-OK {
    param([string] $Text)
    Write-Host "  [OK]  $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string] $Text)
    Write-Host "  [!]   $Text" -ForegroundColor Yellow
}

function Write-Err {
    param([string] $Text)
    Write-Host "  [X]   $Text" -ForegroundColor Red
}

function Invoke-Python {
    param(
        [string] $Script,
        [string] $Descripcion,
        [switch] $AllowFailure
    )

    $scriptPath = Join-Path $Root "scripts\$Script"
    if (-not (Test-Path $scriptPath)) {
        Write-Err "No existe: $scriptPath"
        if (-not $AllowFailure) { exit 2 }
        return $false
    }

    Write-Host "  Ejecutando: $Script" -ForegroundColor Gray
    Write-Host "  $Descripcion" -ForegroundColor Gray
    Write-Host ""

    # Usar call operator (&) para ejecucion confiable con paths con espacios
    & "$PythonPath" "$scriptPath" 2>&1 | ForEach-Object { Write-Host $_ }

    if ($LASTEXITCODE -ne 0) {
        Write-Err "$Script termino con codigo $LASTEXITCODE"
        if (-not $AllowFailure) { exit $LASTEXITCODE }
        return $false
    }

    Write-OK "$Script completado"
    return $true
}

function Move-PDFsToProcesados {
    $pdfs = Get-ChildItem -Path $PdfsNuevos -Filter "*.pdf" -ErrorAction SilentlyContinue
    if (-not $pdfs) { return }

    if (-not (Test-Path $PdfsProcesados)) {
        New-Item -ItemType Directory -Path $PdfsProcesados -Force | Out-Null
    }

    $movidos = 0
    foreach ($pdf in $pdfs) {
        $destino = Join-Path $PdfsProcesados $pdf.Name
        # Si ya existe en procesados, no pisar -- agregar timestamp
        if (Test-Path $destino) {
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $newName = [System.IO.Path]::GetFileNameWithoutExtension($pdf.Name) + "_dup_$timestamp" + $pdf.Extension
            $destino = Join-Path $PdfsProcesados $newName
            Write-Warn "$($pdf.Name) ya existe en procesados -> $newName"
        }
        Move-Item -LiteralPath $pdf.FullName -Destination $destino -Force
        $movidos++
    }

    Write-OK "$movidos PDF(s) movido(s) a pdfs/procesados/"
}

# ============================================================
# BANNER
# ============================================================

Clear-Host
Write-Host ""
Write-Host "  +============================================================+" -ForegroundColor Cyan
Write-Host "  |        ORQUESTADOR DE CARGA DRUPAL -- ANA                   |" -ForegroundColor Cyan
Write-Host "  |        Modo: $(if ($Auto) { 'Automatico' } else { 'Semi-Automatico (con revision)' })" -ForegroundColor Cyan
Write-Host "  +============================================================+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Python: $PythonPath" -ForegroundColor Gray
Write-Host "  Raiz:   $Root" -ForegroundColor Gray
Write-Host ""

# ============================================================
# PASO 0: Verificar que haya PDFs
# ============================================================

Write-Step "PASO 0: Verificando PDFs pendientes"

$pdfsPendientes = Get-ChildItem -Path $PdfsNuevos -Filter "*.pdf" -ErrorAction SilentlyContinue
if (-not $pdfsPendientes) {
    Write-Err "No hay archivos PDF en pdfs/nuevos/"
    Write-Host ""
    Write-Host "  Coloca los PDFs en:" -ForegroundColor Yellow
    Write-Host "    $PdfsNuevos" -ForegroundColor White
    Write-Host ""
    exit 3
}

Write-OK "Encontrados $($pdfsPendientes.Count) PDF(s):"
$pdfsPendientes | ForEach-Object {
    $tipo = "principal"
    if ($_.Name -match '-(PLANO|ANEXO)') { $tipo = "adjunto" }
    Write-Host "    [$tipo] $($_.Name)" -ForegroundColor Gray
}

# ============================================================
# PASO 1: Generar planilla Excel
# ============================================================

Write-Step "PASO 1: Generando planilla Excel" "Cyan"
Invoke-Python -Script "generar_planilla.py" -Descripcion "Extrae metadata de PDFs -> Excel"

# ============================================================
# PASO 2: Revision manual del Excel
# ============================================================

if (-not $Auto) {
    Write-Step "PASO 2: Revision manual del Excel" "Yellow"

    Write-Host "  Se va a abrir el Excel para que revises los datos." -ForegroundColor White
    Write-Host ""
    Write-Host "  VERIFICA especialmente:" -ForegroundColor Yellow
    Write-Host "    - Titulo sugerido (formato RD Nro XXXX-YYYY-ANA-AAA.MDD)" -ForegroundColor Gray
    Write-Host "    - Fecha y hora de la resolucion" -ForegroundColor Gray
    Write-Host "    - Numero de resolucion (sin ceros iniciales)" -ForegroundColor Gray
    Write-Host "    - Resumen del portal" -ForegroundColor Gray
    Write-Host "    - Correspondencia PDF <-> fila" -ForegroundColor Gray
    Write-Host ""

    # Abrir Excel
    Write-Host "  Abriendo Excel..." -ForegroundColor White
    Start-Process -FilePath $ExcelOutput

    Write-Host ""
    Write-Host "  +-----------------------------------------------------+" -ForegroundColor Yellow
    Write-Host "  |  [PAUSA]  REVISA el Excel.                           |" -ForegroundColor Yellow
    Write-Host "  |     1. Corregi lo que haga falta                    |" -ForegroundColor Yellow
    Write-Host "  |     2. Guarda los cambios (Ctrl+G)                  |" -ForegroundColor Yellow
    Write-Host "  |     3. Cerra el Excel (o dejalo abierto)            |" -ForegroundColor Yellow
    Write-Host "  |     4. Volve aca y presiona ENTER                   |" -ForegroundColor Yellow
    Write-Host "  +-----------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""

    Read-Host "  Presiona ENTER cuando hayas terminado de revisar"

    Write-OK "Revision completada. Continuando..."
} else {
    Write-Step "PASO 2: Revision omitida (-Auto)" "Yellow"
    Write-Warn "Modo automatico: se saltea la revision del Excel."
    Write-Warn "Solo usar si los datos ya fueron validados previamente."
}

# ============================================================
# PASO 3: Preparar carga Drupal
# ============================================================

Write-Step "PASO 3: Preparando carga Drupal" "Cyan"
Invoke-Python -Script "preparar_carga_drupal.py" -Descripcion "Convierte Excel -> JSON + detecta adjuntos"

# Mostrar preview de lo que se va a cargar
if (Test-Path $JsonPreview) {
    $json = Get-Content $JsonPreview -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ""
    Write-Host "  Preview de carga:" -ForegroundColor White
    foreach ($rd in $json) {
        $adjCount = $rd.adjuntos.Count
        if ($adjCount -gt 0) {
            Write-Host "    - $($rd.archivo_pdf) -> $($rd.fields.titulo) (+ $adjCount adjuntos)" -ForegroundColor Gray
        } else {
            Write-Host "    - $($rd.archivo_pdf) -> $($rd.fields.titulo)" -ForegroundColor Gray
        }
    }
    Write-Host ""
}

# ============================================================
# PASO 4: CONFIRMACION
# ============================================================

Write-Step "CONFIRMACION" "Magenta"

$totalRDs = (Get-Content $JsonPreview -Raw -Encoding UTF8 | ConvertFrom-Json).Count
Write-Host "  Se van a publicar $totalRDs RD(s) en Drupal ANA." -ForegroundColor White
Write-Host ""
Write-Host "  [!]  Esta accion NO se puede deshacer facilmente." -ForegroundColor Yellow
Write-Host "  [!]  Los PDFs se moveran a pdfs/procesados/ despues de publicar." -ForegroundColor Yellow
Write-Host ""

$confirmacion = Read-Host "  Continuar con la publicacion? (SI/NO)"
if ($confirmacion -notmatch '^(si|si|yes|s|y)$') {
    Write-Host ""
    Write-Warn "Publicacion cancelada por el usuario."
    Write-Host "  Los PDFs siguen en pdfs/nuevos/ para cuando quieras reintentar." -ForegroundColor Gray
    exit 0
}

# ============================================================
# PASO 5: Publicar en Drupal (bot Playwright)
# ============================================================

Write-Step "PASO 5: Publicando en Drupal con bot Playwright" "Cyan"
Write-Host "  El bot va a:" -ForegroundColor White
Write-Host "    - Abrir Chromium" -ForegroundColor Gray
Write-Host "    - Si no hay sesion, pedirte login manual" -ForegroundColor Gray
Write-Host "    - Llenar formulario, subir PDFs + adjuntos" -ForegroundColor Gray
Write-Host "    - Presionar Guardar por cada RD" -ForegroundColor Gray
Write-Host ""

Invoke-Python -Script "subir_a_drupal.py" -Descripcion "Bot Playwright: publica RDs en Drupal"

# ============================================================
# PASO 6: Mover PDFs a procesados
# ============================================================

Write-Step "PASO 6: Archivando PDFs publicados" "Cyan"
Move-PDFsToProcesados

# ============================================================
# FINAL
# ============================================================

Write-Host ""
Write-Host "  +============================================================+" -ForegroundColor Green
Write-Host "  |        FLUJO COMPLETADO!                                    |" -ForegroundColor Green
Write-Host "  +============================================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  PDFs publicados  -> pdfs/procesados/" -ForegroundColor White
Write-Host "  Logs y screenshots -> logs/" -ForegroundColor White
Write-Host "  Excel de revision -> data/resoluciones_pendientes.xlsx" -ForegroundColor White
Write-Host ""

# Mantener ventana abierta si se ejecuto con doble clic
if ($Host.Name -match "ConsoleHost") {
    Write-Host "  Presiona cualquier tecla para cerrar..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
