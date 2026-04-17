#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py makemigrations accounts --no-input
python manage.py makemigrations documents --no-input
python manage.py migrate --no-input

echo "==> Collecting static files..."
python manage.py collectstatic --no-input

echo "==> Seeding initial data (skipped if already seeded)..."
python manage.py seed_data

echo "==> Starting server..."
exec python manage.py runserver 0.0.0.0:8000
