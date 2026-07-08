@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\Activate.ps1" (
    echo First run detected. Installing requirements...
    powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
    if errorlevel 1 pause & exit /b 1
)

powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
pause
