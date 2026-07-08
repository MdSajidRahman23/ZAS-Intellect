if (!(Test-Path "requirements.txt")) {
    Write-Host "Please run this script from the project folder." -ForegroundColor Red
    Write-Host "Example: cd \"D:\ZAS-Intellect\zas_intellect_final_python\"" -ForegroundColor Yellow
    exit 1
}
if (!(Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run .\scripts\setup_windows.ps1 first." -ForegroundColor Red
    exit 1
}
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
