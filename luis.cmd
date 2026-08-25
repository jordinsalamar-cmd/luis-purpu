@echo off
setlocal
set "LUIS_ROOT=%~dp0"
set "LUIS_BIN=%LUIS_ROOT%packages\opencode\dist\opencode-windows-x64\bin\opencode.exe"
set "LUIS_COMPANION_DIR=%LUIS_ROOT%packages\opencode\dist\opencode-windows-x64\bin\luis-companion"
if not exist "%LUIS_BIN%" (
  set "LUIS_BIN=%LUIS_ROOT%packages\opencode\dist-luis\opencode-windows-x64\bin\opencode.exe"
  set "LUIS_COMPANION_DIR=%LUIS_ROOT%packages\opencode\dist-luis\opencode-windows-x64\bin\luis-companion"
)
set "LUIS_GRAPH_ROOT=%LUIS_ROOT%"
set "LUIS_GRAPH_FILE=%LUIS_ROOT%graphify-out\graph.html"
set "LUIS_VRM_PATH=%LUIS_COMPANION_DIR%\assets\luis.vrm"
set "LUIS_CREATOR=JORDIN ARIEL SALAMAR ZAMBRANO"
set "OPENCODE_ENABLE_EXA=1"
set "OPENCODE_ENABLE_PARALLEL=1"
if exist "%LUIS_ROOT%.luis-venv\Scripts\python.exe" set "LUIS_MASCOT_PYTHON=%LUIS_ROOT%.luis-venv\Scripts\python.exe"

if not exist "%LUIS_BIN%" (
  echo No se encontro el build de Luis-Purpu.
  echo Ejecuta install.ps1 antes de usar luis.
  exit /b 1
)

if /I "%~1"=="companion" (
  "%LUIS_BIN%" %*
) else if /I "%~1"=="--version" (
  "%LUIS_BIN%" %*
) else if /I "%~1"=="--help" (
  "%LUIS_BIN%" %*
) else (
  "%LUIS_BIN%" --luis %*
)
set "LUIS_EXIT=%ERRORLEVEL%"
endlocal
exit /b %LUIS_EXIT%
