if (!(Test-Path "requirements.txt")) {
    Write-Host "Please run this script from the project root." -ForegroundColor Red
    Write-Host 'Expected path: D:\ZAS-Intellect\requirements.txt' -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path "app\main.py")) {
    Write-Host "Cannot start: app\main.py is missing." -ForegroundColor Red
    Write-Host 'Move the actual app folder into D:\ZAS-Intellect, or cd into the folder that contains app\main.py.' -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path ".venv\Scripts\Activate.ps1")) {
    Write-Host "Virtual environment not found. Run .\scripts\setup_windows.ps1 first." -ForegroundColor Red
    exit 1
}

.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
