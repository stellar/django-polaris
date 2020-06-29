#!/bin/sh

echo "Applying migrations..."
python manage.py migrate

echo "Creating super user (root, password)..."
python manage.py shell <<EOF

from django.contrib.auth.models import User, Permission

if not User.objects.filter(username="root").exists():
  User.objects.create_superuser("root", None, "password")

EOF
