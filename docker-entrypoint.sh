#!/bin/sh
set -e

# Run migrations and optional seed when starting the web api service
case "$1" in
    gunicorn|python)
        echo "Applying database migrations..."
        python manage.py migrate --noinput

        if [ "$DEMO_MODE" = "True" ] || [ "$DEMO_MODE" = "1" ] || [ "$AUTO_SEED" = "True" ] || [ "$AUTO_SEED" = "1" ]; then
            echo "Seeding initial database state..."
            python manage.py seed || true
        fi
        ;;
esac

exec "$@"
