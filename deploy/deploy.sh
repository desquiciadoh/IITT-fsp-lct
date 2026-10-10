#!/bin/sh
set -eu

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$DEPLOY_DIR")"

echo "=== Deploying FSP Draft Staging ==="
cd "$ROOT_DIR"

echo "1. Pulling latest commits from main..."
git fetch origin main
git checkout main
git pull origin main

echo "2. Building and restarting services..."
docker compose -f deploy/docker-compose.staging.yml pull db redis caddy backup || true
docker compose -f deploy/docker-compose.staging.yml up -d --build

echo "3. Running database migrations..."
docker compose -f deploy/docker-compose.staging.yml exec -T api python manage.py migrate --noinput

echo "4. Collecting static assets..."
docker compose -f deploy/docker-compose.staging.yml exec -T api python manage.py collectstatic --noinput

echo "5. Verifying system checks..."
docker compose -f deploy/docker-compose.staging.yml exec -T api python manage.py check --deploy

echo "=== Deployment finished successfully ==="
