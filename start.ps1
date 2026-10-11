# ==========================================================
#   FSP Draft — Скрипт быстрого запуска для Windows (PowerShell)
#   Использование:
#     .\start.ps1          - Запуск полного стека через Docker Compose
#     .\start.ps1 local    - Запуск локально (manage.py runserver + pnpm dev)
#     .\start.ps1 test     - Запуск тестов
# ==========================================================

param (
    [string]$Mode = "docker"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  FSP Draft — Платформа обратного IT-рекрутинга" -ForegroundColor Cyan
Write-Host "  Режим запуска: $Mode" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "Копирование .env.example -> .env..." -ForegroundColor Yellow
    Copy-Item .env.example .env
}

if ($Mode -eq "test") {
    Write-Host "`n▶ Запуск тестов Backend..." -ForegroundColor Green
    if (Test-Path ".venv\Scripts\pytest.exe") {
        & .venv\Scripts\pytest.exe
    } else {
        pytest
    }

    if (Test-Path "web\package.json") {
        Write-Host "`n▶ Запуск тестов Frontend..." -ForegroundColor Green
        pnpm --dir web test
    }
    exit 0
}

if ($Mode -eq "local") {
    Write-Host "`n▶ Запуск в локальном режиме..." -ForegroundColor Green
    $pythonExe = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

    Write-Host "Применение миграций базы данных..." -ForegroundColor Yellow
    & $pythonExe manage.py migrate --noinput

    Write-Host "Загрузка тестовых данных (seed)..." -ForegroundColor Yellow
    & $pythonExe manage.py seed

    Write-Host "`n✅ Сервисы готовы к запуску!" -ForegroundColor Green
    Write-Host "🔗 Веб-приложение:  http://localhost:5173" -ForegroundColor Cyan
    Write-Host "🔗 API & Swagger:    http://localhost:8000/api/docs/" -ForegroundColor Cyan
    Write-Host "🔗 Админ-панель:    http://localhost:8000/admin/" -ForegroundColor Cyan

    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'Запуск Django API...'; & '$pythonExe' manage.py runserver 0.0.0.0:8000"
    if (Test-Path "web") {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "Write-Host 'Запуск Web Frontend...'; Set-Location web; pnpm dev"
    }
    Write-Host "`nСерверы запущены в отдельных окнах терминала!" -ForegroundColor Green
} else {
    Write-Host "`n▶ Запуск всех сервисов через Docker Compose..." -ForegroundColor Green
    Write-Host "🔗 Веб-приложение:  http://localhost:5173" -ForegroundColor Cyan
    Write-Host "🔗 API & Swagger:    http://localhost:8000/api/docs/" -ForegroundColor Cyan
    Write-Host "🔗 Админ-панель:    http://localhost:8000/admin/" -ForegroundColor Cyan
    Write-Host "🔗 Почта (MailHog): http://localhost:8025" -ForegroundColor Cyan
    Write-Host ""
    docker compose up --build
}
