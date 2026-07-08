if (!(Test-Path "requirements.txt")) {
    Write-Host "Please run this script from the project folder." -ForegroundColor Red
    exit 1
}
if (Test-Path "zas_intellect.db") {
    Remove-Item "zas_intellect.db"
}
if (Test-Path "app\data\uploads") {
    Get-ChildItem "app\data\uploads" -File | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Force
}
if (Test-Path "app\data\recordings") {
    Get-ChildItem "app\data\recordings" -Recurse -Force | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Force -Recurse
}
if (Test-Path ".venv\Scripts\Activate.ps1") {
    .\.venv\Scripts\Activate.ps1
}
python -m app.seed
Write-Host "Database reset complete." -ForegroundColor Green
