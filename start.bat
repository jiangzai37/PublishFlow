@echo off
setlocal
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;E:\AI\tools\_bin;E:\node.js;%PATH%"
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%UV%" set "UV=E:\AI\tools\_bin\uv.exe"
if not exist "%UV%" for %%I in (uv.exe) do set "UV=%%~$PATH:I"
if not exist "%UV%" (
  echo uv was not found. Install uv or add it to PATH.
  pause
  exit /b 1
)
set "NPM=E:\node.js\npm.cmd"
if not exist "%NPM%" (
  where npm
  if errorlevel 1 (
    echo npm was not found. Install Node.js 22+ or add it to PATH.
    pause
    exit /b 1
  )
  set "NPM=npm.cmd"
)
if not exist ".venv" (
  "%UV%" venv .venv
  "%UV%" pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
)
if not exist "frontend\node_modules" (
  call "%NPM%" --prefix frontend ci
)
.venv\Scripts\python.exe scripts\dev.py
set "exit_code=%errorlevel%"
if not "%exit_code%"=="0" pause
exit /b %exit_code%
