FROM python:3.12-bullseye
LABEL authors="Leander Schulten"

ADD requirements.txt /app/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends netcat

RUN set -ex \
    && python -m venv /env \
    && /env/bin/pip install --upgrade pip \
    && /env/bin/pip install --no-cache-dir -r /app/requirements.txt gunicorn setuptools psycopg2-binary==2.9.6


ADD . /app
WORKDIR /app

ENV VIRTUAL_ENV /env
ENV PATH /env/bin:$PATH

RUN python manage.py collectstatic --noinput

ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8000
CMD ["gunicorn", "--bind", ":8000", "--workers", "3", "schwarzzeltland.wsgi:application"]
