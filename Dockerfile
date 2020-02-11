# Python version
FROM python:3.7-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apk update && apk add build-base postgresql-dev libffi-dev gettext-dev curl

# Copy files to working directory
RUN mkdir /code /code/polaris
COPY ./example ./setup.py ./README.rst ./MANIFEST.in /code/
COPY ./polaris /code/polaris/

# Set fake environment variables so manage.py commands can run.
# django-environ's env() function uses variables defined in the
# environment over matching variables in the .env file, so these
# variables will be overidden in production, and won't be defined
# if a .env file already exists.
RUN if [ ! -f /code/.env ]; then echo $'\
ASSETS=FAKE\n\
FAKE_DISTRIBUTION_ACCOUNT_SEED=SB4XM7E6ZP4NIQF3UNVMX5O5NH7RGHFHDLIS4Z5U4OMNQ7T4EDNKPVNU\n\
FAKE_ISSUER_ACCOUNT_ADDRESS=GCYPVLFODQNRZAQTDBIZMBJ5QNSBYBXGM7KWHGS2SFIU73BTTDNSTWDH\n\
HOST_URL=https://fake.com\n\
SERVER_JWT_KEY=notsosecretkey\n\
DJANGO_SECRET_KEY=notsosecretkey\
' >> /code/.env; fi

# Install dependencies
WORKDIR /code
RUN pip install pipenv; pipenv install --dev --system

# Create .po and .mo translation files
WORKDIR /code/polaris/polaris
RUN django-admin compilemessages
WORKDIR /code/server
RUN django-admin compilemessages

WORKDIR /code

# Compile static assets, collect static assets, run migrations
RUN python manage.py compilescss; python manage.py collectstatic --no-input -v 0

# Overridden by heroku.yml's run phrase in deployment
CMD python manage.py migrate; python manage.py runsslserver --nostatic --certificate cert.pem --key key.pem 0.0.0.0:8000