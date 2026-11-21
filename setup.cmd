@echo off
setlocal
pushd "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m venv .venv
) else (
  py -3.11 -m venv .venv
)
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -e ".[audio]"
if errorlevel 1 goto fail
echo.
echo Ready. Run brain.cmd init, then brain.cmd index "your folder".
echo Run brain.cmd serve to open the local app.
popd
exit /b 0
:fail
echo Setup could not finish. Install Python 3.11 and retry. See README.md for manual setup.
popd
exit /b 1
