Write-Host "Setting up ZAS-Intellect Adaptive Viva Demo..." -ForegroundColor Green

if (!(Test-Path "requirements.txt")) {
    Write-Host "requirements.txt not found. Please run this script from the project root." -ForegroundColor Red
    Write-Host 'Expected path: D:\ZAS-Intellect\requirements.txt' -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path "app\main.py")) {
    Write-Host "App code not found: app\main.py is missing." -ForegroundColor Red
    Write-Host "Your actual project files are probably still inside a nested folder or were not copied here." -ForegroundColor Yellow
    Write-Host 'Fix target: README.md, requirements.txt, app\, templates\, static\, scripts\ should be directly inside D:\ZAS-Intellect' -ForegroundColor Yellow
    exit 1
}

if (!(Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example" -ForegroundColor Cyan
    } else {
        @"
APP_NAME=ZAS-Intellect
APP_SECRET_KEY=change-this-demo-secret-before-production
DEMO_MODE=true
SHOW_DEMO_CREDENTIALS=true
DATABASE_URL=sqlite:///./zas_intellect.db
SECURE_COOKIES=false
PRODUCTION_MODE=false
AI_PROVIDER=auto
XAI_API_KEY=
XAI_MODEL=grok-4.3
GEMINI_API_KEY=
STT_PROVIDER=browser
"@ | Set-Content ".env" -Encoding UTF8
        Write-Host "Created default .env" -ForegroundColor Cyan
    }
}

if (!(Test-Path ".venv\Scripts\Activate.ps1")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m app.seed
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database seeding failed. Check whether app\seed.py exists and imports correctly." -ForegroundColor Red
    exit 1
}

Write-Host "Setup complete. Run .\scripts\start_windows.ps1" -ForegroundColor Green
