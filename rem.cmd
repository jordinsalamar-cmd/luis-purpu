@echo off
setlocal
set "REM_ROOT=%~dp0"
set "REM_BIN=%REM_ROOT%packages\opencode\dist\opencode-windows-x64\bin\opencode.exe"
set "REM_COMPANION_DIR=%REM_ROOT%packages\opencode\dist\opencode-windows-x64\bin\luis-companion"
if not exist "%REM_BIN%" (
  set "REM_BIN=%REM_ROOT%packages\opencode\dist-rem\opencode-windows-x64\bin\opencode.exe"
  set "REM_COMPANION_DIR=%REM_ROOT%packages\opencode\dist-rem\opencode-windows-x64\bin\luis-companion"
)
set "LUIS_ROOT=%REM_ROOT%"
set "LUIS_BIN=%REM_BIN%"
set "LUIS_COMPANION_DIR=%REM_COMPANION_DIR%"
set "LUIS_GRAPH_ROOT=%REM_ROOT%"
set "LUIS_GRAPH_FILE=%REM_ROOT%graphify-out\rem-memory.html"
set "LUIS_VRM_PATH=%REM_COMPANION_DIR%\assets\rem.vrm"
set "LUIS_CREATOR=JORDIN ARIEL SALAMAR ZAMBRANO"
if not defined LUIS_TTS_MODE set "LUIS_TTS_MODE=auto"
set "OPENCODE_ENABLE_EXA=1"
set "OPENCODE_ENABLE_PARALLEL=1"
if exist "%REM_ROOT%.luis-venv\Scripts\python.exe" set "LUIS_MASCOT_PYTHON=%REM_ROOT%.luis-venv\Scripts\python.exe"

if not exist "%REM_BIN%" (
  echo No se encontro la instalacion de Rem.
  echo Ejecuta install.ps1 antes de usar rem.
  exit /b 1
)

if /I "%~1"=="companion" (
  "%REM_BIN%" %*
) else if /I "%~1"=="--version" (
  "%REM_BIN%" %*
) else if /I "%~1"=="--help" (
  "%REM_BIN%" %*
) else (
  "%REM_BIN%" --luis %*
)
set "REM_EXIT=%ERRORLEVEL%"
endlocal
exit /b %REM_EXIT%
