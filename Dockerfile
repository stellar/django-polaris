# Python version
FROM python:3.7-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apk update && apk add build-base postgresql-dev postgresql-client libffi-dev python3-dev cargo gettext-dev curl

# Copy files to working directory
RUN mkdir /code /code/polaris /code/data
COPY ./example ./setup.py ./README.rst ./MANIFEST.in /code/
COPY ./polaris /code/polaris/

# Set fake environment variables so manage.py commands can run.
# django-environ's env() function uses variables defined in the
# environment over matching variables in the .env file, so these
# variables will be overidden in production, and won't be defined
# if a .env file already exists.
RUN if [ ! -f /code/.env ]; then echo $'\
SIGNING_SEED=SB4XM7E6ZP4NIQF3UNVMX5O5NH7RGHFHDLIS4Z5U4OMNQ7T4EDNKPVNU\n\
HOST_URL=https://fake.com\n\
SERVER_JWT_KEY=notsosecretkey\n\
DJANGO_SECRET_KEY=notsosecretkey\n\
ACTIVE_SEPS=\
' >> /code/.env; fi

# Install dependencies
WORKDIR /code
RUN pip install pipenv; pipenv install --dev --system

# collect static assets
RUN python manage.py collectstatic --no-input --ignore=*.scss

# Overridden by heroku.yml's run phrase in deployment
CMD python manage.py migrate; python manage.py runserver --nostatic 0.0.0.0:8000