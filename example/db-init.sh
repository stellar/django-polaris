#!/bin/sh

echo "Applying migrations..."
python manage.py migrate

echo "Creating assets defined in environment..."
python manage.py shell <<EOF

import os
from polaris.models import Asset

Asset.objects.get_or_create(
  code="SRT",
  issuer=os.environ["SRT_ISSUER_ACCOUNT_ADDRESS"],
  distribution_seed=os.environ["SRT_DISTRIBUTION_ACCOUNT_SEED"]
)

EOF

echo "Creating super user (root, password)..."
python manage.py shell <<EOF

from django.contrib.auth.models import User, Permission

if not User.objects.filter(username="root").exists():
  User.objects.create_superuser("root", None, "password")

EOF
