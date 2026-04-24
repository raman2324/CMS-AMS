#!/bin/sh
set -e

echo "==> Ensuring S3/MinIO bucket exists..."
python << 'PYEOF'
import os, sys
bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
if bucket:
    import boto3
    from botocore.exceptions import ClientError
    endpoint = os.environ.get('AWS_S3_ENDPOINT_URL') or None
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=os.environ.get('AWS_S3_REGION_NAME', 'us-east-1'),
        verify=not bool(endpoint),  # False for MinIO (HTTP), True for real S3 (HTTPS)
    )
    try:
        s3.create_bucket(Bucket=bucket)
        print(f"S3 bucket '{bucket}' created.")
    except ClientError as e:
        code = e.response['Error']['Code']
        if code in ('BucketAlreadyExists', 'BucketAlreadyOwnedByYou'):
            print(f"S3 bucket '{bucket}' already exists.")
        else:
            print(f"S3 bucket error: {e}", file=sys.stderr)
            sys.exit(1)
PYEOF

echo "==> Running migrations..."
python manage.py makemigrations --no-input
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
