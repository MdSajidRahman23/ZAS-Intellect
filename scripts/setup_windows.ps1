Write-Host "Setting up ZAS-Intellect Adaptive Viva Demo..." -ForegroundColor Green

if (!(Test-Path "requirements.txt")) {
    Write-Host "requirements.txt not found. Please run this script from the project folder." -ForegroundColor Red
    Write-Host "Example: cd \"D:\ZAS-Intellect\zas_intellect_final_python\"" -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example" -ForegroundColor Cyan
}

if (!(Test-Path ".venv\Scripts\Activate.ps1")) {
    python -m venv .venv
}
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m app.seed
Write-Host "Setup complete. Run .\scripts\start_windows.ps1" -ForegroundColor Green
