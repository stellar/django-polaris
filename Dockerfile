FROM python:3.7-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

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
    poetry install -E server --no-dev && \
    ENV_PATH=/code/.env.example \
    poetry run python manage.py collectstatic --no-input --ignore='*.scss'

CMD poetry run python manage.py runserver --nostatic 0.0.0.0:8000