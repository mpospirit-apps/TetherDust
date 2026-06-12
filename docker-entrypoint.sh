#!/bin/bash
set -e

cd /app/tetherdust/web

# Wait for PostgreSQL to be ready (safety net alongside Docker health checks)
if [ -n "$DB_HOST" ]; then
    echo "Waiting for PostgreSQL at $DB_HOST:${DB_PORT:-5432}..."
    until python -c "
import socket, sys
try:
    s = socket.create_connection(('$DB_HOST', ${DB_PORT:-5432}), timeout=2)
    s.close()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        sleep 1
    done
    echo "PostgreSQL is ready."
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Create superuser if it doesn't exist
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    echo "Ensuring superuser exists..."
    python manage.py createsuperuser --noinput 2>/dev/null || true
fi

# Auto-discover documentation sources from filesystem
echo "Syncing documentation sources..."
python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tetherdust_web.settings')
import django; django.setup()
from core.models import DocumentationSource
result = DocumentationSource.sync_from_filesystem()
if result['created']:
    print(f'  Created: {result[\"created\"]}')
if result['deactivated']:
    print(f'  Deactivated: {result[\"deactivated\"]}')
if not result['created'] and not result['deactivated']:
    print('  No changes.')
"

# Ensure all users have a UserProfile (handles pre-existing superusers)
echo "Ensuring user profiles exist..."
python -c "
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tetherdust_web.settings')
import django; django.setup()
from django.contrib.auth import get_user_model
from core.models import UserProfile, Role
User = get_user_model()
admin_role = Role.objects.filter(name='Admin').first()
for user in User.objects.all():
    profile, created = UserProfile.objects.get_or_create(
        user=user,
        defaults={'role': admin_role if user.is_superuser else None},
    )
    if created:
        print(f'  Created profile for {user.username} (role={profile.role})')
    elif not profile.role and user.is_superuser and admin_role:
        profile.role = admin_role
        profile.save(update_fields=['role'])
        print(f'  Assigned Admin role to {user.username}')
"

# In debug mode use Django's dev server (auto-reloads on file changes).
# Django Channels overrides runserver to be ASGI + WebSocket capable.
# In production use Daphne.
if [ "$DJANGO_DEBUG" = "true" ]; then
    echo "Starting TetherDust dev server on port 8000 (auto-reload enabled)..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting TetherDust on port 8000..."
    exec daphne -b 0.0.0.0 -p 8000 tetherdust_web.asgi:application
fi
