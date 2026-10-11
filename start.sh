#!/usr/bin/env bash
set -e

# ==========================================================
#   FSP Draft — Скрипт быстрого запуска (Quick Start)
#   Использование:
#     ./start.sh          - Запуск полного стека через Docker Compose (рекомендуется)
#     ./start.sh local    - Запуск локально (Python manage.py + pnpm dev)
#     ./start.sh test     - Запуск полного набора автотестов
# ==========================================================

MODE="${1:-docker}"

echo "=========================================================="
echo "  FSP Draft — Платформа обратного IT-рекрутинга"
echo "  Режим запуска: $MODE"
echo "=========================================================="

if [ ! -f ".env" ]; then
    echo "📄 Файл .env не найден. Создаём копию из .env.example..."
    cp .env.example .env
fi

if [ "$MODE" = "test" ]; then
    echo "▶ Запуск тестов Backend (pytest)..."
    if [ -f ".venv/bin/pytest" ]; then
        .venv/bin/pytest
    else
        pytest
    fi

    if [ -d "web" ] && command -v pnpm &> /dev/null; then
        echo "▶ Запуск тестов Frontend (vitest)..."
        (cd web && pnpm test)
    fi
    exit 0
fi

if [ "$MODE" = "local" ]; then
    echo "▶ Режим локального запуска..."

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        source venv/bin/activate
    fi

    echo "📦 Применение миграций базы данных..."
    python manage.py migrate --noinput

    echo "🌱 Загрузка демонстрационных данных (seed)..."
    python manage.py seed || true

    echo ""
    echo "✅ Сервер готов к запуску!"
    echo "🔗 Веб-приложение:  http://localhost:5173"
    echo "🔗 API & Swagger:    http://localhost:8000/api/docs/"
    echo "🔗 Админ-панель:    http://localhost:8000/admin/"
    echo ""

    python manage.py runserver 0.0.0.0:8000 &
    BACKEND_PID=$!

    if [ -d "web" ] && command -v pnpm &> /dev/null; then
        (cd web && pnpm dev) &
        FRONTEND_PID=$!
    fi

    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT INT TERM
    wait
else
    echo "▶ Запуск всех сервисов через Docker Compose..."
    echo "  (PostgreSQL pgvector, Redis, Django API, Celery Workers, MailHog, Web Frontend)"
    echo ""
    echo "🔗 Веб-приложение:  http://localhost:5173"
    echo "🔗 API & Swagger:    http://localhost:8000/api/docs/"
    echo "🔗 Админ-панель:    http://localhost:8000/admin/"
    echo "🔗 Почта (MailHog): http://localhost:8025"
    echo ""
    docker compose up --build
fi
