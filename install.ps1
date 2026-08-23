[CmdletBinding()]
param(
  [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path

function Step([string]$Message) {
  Write-Host "[Luis] $Message" -ForegroundColor Cyan
}

function Find-Python {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $resolved = (& $py.Source -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
    if ($LASTEXITCODE -eq 0 -and $resolved) { return $resolved }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return $python.Source }
  return $null
}

function Find-Bun {
  $bun = Get-Command bun -ErrorAction SilentlyContinue
  if ($bun) { return $bun.Source }
  $candidate = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
  if (Test-Path -LiteralPath $candidate) { return $candidate }
  return $null
}

Set-Location -LiteralPath $ProjectRoot
$python = Find-Python
if (-not $python) { throw "Python 3 no está instalado. Instálalo desde https://www.python.org/downloads/ y repite." }

$bun = Find-Bun
if (-not $bun) {
  Step "Bun no está instalado; instalándolo para este usuario..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://bun.sh/install.ps1 | iex"
  $bun = Find-Bun
}
if (-not $bun) { throw "No se pudo localizar Bun después de instalarlo." }

Step "Instalando dependencias de Luis..."
& $bun install --frozen-lockfile

$venv = Join-Path $ProjectRoot ".luis-venv"
if (-not (Test-Path -LiteralPath $venv)) { & $python -m venv $venv }
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) { throw "No se pudo crear el entorno de voz de Luis." }

Step "Instalando voz, micrófono y visión del companion..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r "packages\opencode\resources\luis-companion\requirements.txt"
if (-not $SkipBrowserInstall) { & $venvPython -m playwright install chromium }

Step "Compilando el terminal de Luis-Purpu..."
& $bun run --cwd packages/opencode build --single --skip-install --skip-embed-web-ui

$build = Join-Path $ProjectRoot "packages\opencode\dist\opencode-windows-x64"
$portable = Join-Path $ProjectRoot "packages\opencode\dist-luis\opencode-windows-x64"
if (-not (Test-Path -LiteralPath (Join-Path $build "bin\opencode.exe"))) { throw "El build no generó el ejecutable de Luis." }
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $portable) -Force | Out-Null
Copy-Item -LiteralPath $build -Destination $portable -Recurse -Force

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($userPath -split ";") -contains $ProjectRoot)) {
  [Environment]::SetEnvironmentVariable("Path", (($userPath, $ProjectRoot | Where-Object { $_ }) -join ";"), "User")
}
$env:Path = "$ProjectRoot;$env:Path"

Step "Validando ejecutable y launcher..."
$version = & (Join-Path $ProjectRoot "luis.cmd") --version
if ($LASTEXITCODE -ne 0) { throw "El launcher no pudo iniciar." }
Write-Host "Luis-Purpu instalado: $version" -ForegroundColor Green
Write-Host "Creador: Jordin Ariel Salamar Zambrano" -ForegroundColor DarkGray
Write-Host "Ejecuta 'luis' en una terminal nueva." -ForegroundColor Green
