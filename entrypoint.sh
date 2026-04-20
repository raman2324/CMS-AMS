#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py makemigrations accounts --no-input
python manage.py makemigrations documents --no-input
python manage.py makemigrations uploads --no-input
python manage.py migrate --no-input

echo "==> Collecting static files..."
python manage.py collectstatic --no-input

echo "==> Seeding initial data (skipped if already seeded)..."
python manage.py seed_data

echo "==> Encrypting existing files (no-op if already encrypted or key not set)..."
python manage.py encrypt_existing_files

echo "==> Starting server..."
if [ "${DEBUG:-True}" = "False" ]; then
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
else
    exec python manage.py runserver 0.0.0.0:8000
fi
