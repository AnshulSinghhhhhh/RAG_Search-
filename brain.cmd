@echo off
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" -m secondbrain %*
) else (
  python -m secondbrain %*
)
exit /b %errorlevel%
