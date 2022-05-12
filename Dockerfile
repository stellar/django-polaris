FROM python:3.7-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV POETRY_CACHE_DIR /code/.cache/pypoetry

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    cargo \
    postgresql \
    postgresql-client \
    gettext

WORKDIR /code
COPY . .

RUN pip install poetry &&  \
    poetry install --no-dev -E dev-server && \
    ENV_PATH=/code/.env.example \
    poetry run python manage.py collectstatic --no-input --ignore='*.scss'

CMD poetry run python manage.py runserver --nostatic 0.0.0.0:8000