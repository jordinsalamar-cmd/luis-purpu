[CmdletBinding()]
param(
  [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path

function Step([string]$Message) {
  Write-Host "[Rem] $Message" -ForegroundColor Cyan
}

function Find-Python {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    $resolved = (& $py.Source -3 -c "import sys; print(sys.executable)" 2>$null).Trim()
    if ($LASTEXITCODE -eq 0 -and $resolved) { return $resolved }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    $resolved = (& $python.Source -c "import sys; print(sys.executable)" 2>$null).Trim()
    if ($LASTEXITCODE -eq 0 -and $resolved) { return $resolved }
  }
  $known = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path ${env:ProgramFiles} "Python312\python.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Python312\python.exe")
  )
  foreach ($candidate in $known) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  return $null
}

function Find-Bun {
  $bun = Get-Command bun -ErrorAction SilentlyContinue
  if ($bun) { return $bun.Source }
  $candidate = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
  if (Test-Path -LiteralPath $candidate) { return $candidate }
  return $null
}

function Refresh-ProcessPath {
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $env:Path = (($userPath, $machinePath | Where-Object { $_ }) -join ";")
}

function Install-RemLauncher {
  param([string]$Root)

  # A stable launcher must win over old global npm/Bun installs. It delegates
  # to this checkout, so reinstalling or updating the project always changes
  # what `rem` runs without leaving duplicate versions on PATH.
  $launcherRoot = Join-Path $env:LOCALAPPDATA "Rem\bin"
  $launcher = Join-Path $launcherRoot "rem.cmd"
  $legacyLauncherRoot = Join-Path $env:LOCALAPPDATA "Luis-Purpu\bin"
  $legacyLauncher = Join-Path $legacyLauncherRoot "luis.cmd"
  if (Test-Path -LiteralPath $legacyLauncher) {
    Remove-Item -LiteralPath $legacyLauncher -Force -ErrorAction SilentlyContinue
  }
  New-Item -ItemType Directory -Path $launcherRoot -Force | Out-Null
  $launcherText = @"
@echo off
setlocal
pushd "$Root"
call "$Root\rem.cmd" %*
set "LUIS_EXIT=%ERRORLEVEL%"
popd
endlocal & exit /b %LUIS_EXIT%
"@
  Set-Content -LiteralPath $launcher -Value $launcherText -Encoding ASCII

  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $pathEntries = @($userPath -split ";" | Where-Object {
      $_ -and ($_ -ne $Root) -and ($_ -ne $launcherRoot) -and ($_ -ne $legacyLauncherRoot)
    })
  [Environment]::SetEnvironmentVariable("Path", (($launcherRoot, $pathEntries) -join ";"), "User")
  $env:Path = "$launcherRoot;$env:Path"
  return $launcher
}

function Install-FfmpegDirect {
  $toolsRoot = Join-Path $env:LOCALAPPDATA "Rem\ffmpeg"
  $zip = Join-Path $env:TEMP "rem-ffmpeg.zip"
  $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

  Step "winget no está disponible; descargando FFmpeg directamente..."
  New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
  Expand-Archive -LiteralPath $zip -DestinationPath $toolsRoot -Force
  Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue

  $ffplayPath = Get-ChildItem -LiteralPath $toolsRoot -Filter "ffplay.exe" -File -Recurse |
    Select-Object -First 1 -ExpandProperty FullName
  if (-not $ffplayPath) { throw "No se pudo localizar ffplay después de descargar FFmpeg." }

  $ffmpegBin = Split-Path -Parent $ffplayPath
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $entries = @($userPath -split ";" | Where-Object { $_ })
  if ($entries -notcontains $ffmpegBin) {
    [Environment]::SetEnvironmentVariable("Path", (($ffmpegBin, $entries) -join ";"), "User")
  }
  $env:Path = "$ffmpegBin;$env:Path"
  return (Get-Command ffplay -ErrorAction SilentlyContinue)
}

function Install-WingetPackage([string]$Id, [string]$Label) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) {
    throw "No encuentro winget. Instala App Installer desde Microsoft Store y repite la instalación de Re:ZERO."
  }
  Step "Instalando $Label automáticamente..."
  & $winget.Source install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements --silent
  if ($LASTEXITCODE -ne 0) { throw "winget no pudo instalar $Label (código $LASTEXITCODE)." }
  Refresh-ProcessPath
}

Set-Location -LiteralPath $ProjectRoot
$python = Find-Python
if (-not $python) {
  Install-WingetPackage "Python.Python.3.12" "Python 3.12"
  $python = Find-Python
}
if (-not $python) { throw "No se pudo localizar Python 3 después de instalarlo." }

$bun = Find-Bun
if (-not $bun) {
  Step "Bun no está instalado; instalándolo para este usuario..."
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://bun.sh/install.ps1 | iex"
  Refresh-ProcessPath
  $bun = Find-Bun
}
if (-not $bun) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) { throw "No se pudo instalar Bun desde bun.sh y no encuentro winget. Instala App Installer y repite la instalación de Re:ZERO." }
  Step "La descarga directa de Bun falló; instalándolo con winget..."
  & $winget.Source install --id Oven-sh.Bun --exact --source winget --accept-source-agreements --accept-package-agreements --silent
  if ($LASTEXITCODE -ne 0) { throw "winget no pudo instalar Bun (código $LASTEXITCODE)." }
  Refresh-ProcessPath
  $bun = Find-Bun
}
if (-not $bun) { throw "No se pudo localizar Bun después de instalarlo." }

$ffplay = Get-Command ffplay -ErrorAction SilentlyContinue
if (-not $ffplay) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    Install-WingetPackage "Gyan.FFmpeg.Shared" "FFmpeg (audio para la voz online)"
    $ffplay = Get-Command ffplay -ErrorAction SilentlyContinue
  }
  if (-not $ffplay) { $ffplay = Install-FfmpegDirect }
}
if (-not $ffplay) { throw "No se pudo localizar ffplay después de instalar FFmpeg." }

Step "Instalando dependencias de Rem..."
& $bun install --frozen-lockfile

$venv = Join-Path $ProjectRoot ".luis-venv"
if (-not (Test-Path -LiteralPath $venv)) { & $python -m venv $venv }
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) { throw "No se pudo crear el entorno de voz de Rem." }

Step "Instalando voz, micrófono y visión del companion de Rem..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r "packages\opencode\resources\luis-companion\requirements.txt"
$piperDir = Join-Path $ProjectRoot "packages\opencode\resources\luis-companion\models\piper"
$piperModel = Join-Path $piperDir "es_MX-claude-high.onnx"
if (-not (Test-Path -LiteralPath $piperModel)) {
  Step "Descargando voz local femenina de Rem..."
  New-Item -ItemType Directory -Path $piperDir -Force | Out-Null
  & $venvPython -m piper.download_voices --download-dir $piperDir es_MX-claude-high
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $piperModel)) {
    throw "No se pudo descargar la voz local de Rem."
  }
}
if (-not $SkipBrowserInstall) { & $venvPython -m playwright install chromium }

Step "Compilando el terminal de Re:ZERO..."
& $bun run --cwd packages/opencode build --single --skip-install --skip-embed-web-ui

$build = Join-Path $ProjectRoot "packages\opencode\dist\opencode-windows-x64"
$portable = Join-Path $ProjectRoot "packages\opencode\dist-rem\opencode-windows-x64"
if (-not (Test-Path -LiteralPath (Join-Path $build "bin\opencode.exe"))) { throw "El build no generó el ejecutable de Re:ZERO." }
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Recurse -Force }
New-Item -ItemType Directory -Path (Split-Path $portable) -Force | Out-Null
Copy-Item -LiteralPath $build -Destination $portable -Recurse -Force

$launcher = Install-RemLauncher -Root $ProjectRoot

Step "Validando ejecutable y launcher..."
$version = & $launcher --version
if ($LASTEXITCODE -ne 0) { throw "El launcher no pudo iniciar." }
Write-Host "Re:ZERO instalado: $version" -ForegroundColor Green
Write-Host "Creador: Jordin Ariel Salamar Zambrano" -ForegroundColor DarkGray
Write-Host "Ejecuta 'rem' en una terminal nueva; siempre apuntará a esta versión." -ForegroundColor Green
