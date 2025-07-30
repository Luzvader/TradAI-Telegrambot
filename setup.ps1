<#
    Instalador de TradAI (PowerShell)
    --------------------------------
    - Crea/activa un entorno virtual de Python (si no existe)
    - Instala dependencias Python (requirements.txt)
    - Instala dependencias del frontend (Next.js) evitando problemas de ExecutionPolicy
    Ejecuta con:
        powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

param(
    [string]$PythonExe = "python"
)

function Write-Section($msg) {
    Write-Host "`n=== $msg ===`n" -ForegroundColor Cyan
}

# 1. Python virtualenv
$venvPath = Join-Path $PSScriptRoot ".venv"
Write-Section "Entorno virtual de Python"
if (!(Test-Path $venvPath)) {
    & $PythonExe -m venv $venvPath
}
$env:VIRTUAL_ENV = $venvPath
$env:PATH = "$venvPath\Scripts;" + $env:PATH
Write-Host "Activado venv en $venvPath"

# 2. Dependencias backend
Write-Section "Dependencias Python"
& pip install -r (Join-Path $PSScriptRoot "requirements.txt")

# 3. Dependencias frontend
Write-Section "Dependencias Frontend (npm)"
$frontendDir = Join-Path $PSScriptRoot "frontend"
Push-Location $frontendDir
# Detectar si npm está disponible
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
if (-not $npm) {
    Write-Host "npm no está instalado o no está en PATH. Omite instalación de dependencias frontend. Descarga Node.js de https://nodejs.org/ si quieres usar la interfaz web." -ForegroundColor Yellow
} elseif (!(Test-Path "node_modules")) {
    & $npm install
} else {
    Write-Host "node_modules ya existe, omitiendo npm install"
}
Pop-Location

Write-Section "Instalación completada"
