FROM python:3.12-bullseye
LABEL authors="Leander Schulten"

ADD requirements.txt /app/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends netcat

RUN set -ex \
    && python -m venv /env \
    && /env/bin/pip install --upgrade pip \
    && /env/bin/pip install --no-cache-dir -r /app/requirements.txt setuptools psycopg2-binary==2.9.6


ADD . /app
WORKDIR /app

ENV VIRTUAL_ENV /env
ENV PATH /env/bin:$PATH

ENTRYPOINT ["/app/docker-entrypoint.sh"]

EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "schwarzzeltland.asgi:application"]
