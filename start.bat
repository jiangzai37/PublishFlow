@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul || (echo 未找到 uv，请先安装 uv。 & pause & exit /b 1)
where npm >nul 2>nul || (echo 未找到 npm，请先安装 Node.js 22+。 & pause & exit /b 1)
if not exist ".venv" (
  uv venv .venv
  uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
)
if not exist "frontend\node_modules" (
  npm --prefix frontend ci
)
.venv\Scripts\python.exe scripts\dev.py
set "exit_code=%errorlevel%"
if not "%exit_code%"=="0" pause
exit /b %exit_code%
