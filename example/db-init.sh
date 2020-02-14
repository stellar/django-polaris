#!/bin/sh

echo "Applying migrations..."
python manage.py migrate

echo "Creating assets defined in settings (read from environment)..."
python manage.py shell <<EOF

from polaris.models import Asset
from polaris import settings

for code in settings.ASSETS:
    print(f"Creating {code}...")
    Asset.objects.get_or_create(code=code, issuer=settings.ASSETS[code]["ISSUER_ACCOUNT_ADDRESS"])

EOF

echo "Creating super user (root, password)..."
python manage.py shell <<EOF

from django.contrib.auth.models import User, Permission

if not User.objects.filter(username="root").exists():
  User.objects.create_superuser("root", None, "password")

EOF
