#!/bin/sh
set -e

# Collect static files before stating the server
python manage.py collectstatic --noinput

if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL started"
fi

# Migrate DB before starting the server
python manage.py migrate --noinput

exec "$@"