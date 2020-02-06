# Python version
FROM python:3.7-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update && apk add build-base postgresql-dev libffi-dev gettext-dev

# Copy files to working directory
RUN mkdir /code
#COPY ./polaris /code/
#RUN mkdir /code/server
#COPY ./example/server /code/server/
#COPY ./Pipfile ./Pipfile.lock /code/
COPY ./example /code
COPY ./setup.py ./README.rst ./MANIFEST.in /code/
RUN mkdir /code/polaris
RUN mkdir /code/polaris/polaris
COPY ./polaris/polaris /code/polaris/polaris/

# Install dependencies
WORKDIR /code
#RUN pip install virtualenv
#RUN virtualenv -p python3 .venv
#RUN . .venv/bin/activate
#WORKDIR /code/polaris
#RUN python setup.py egg_info
RUN pip install pipenv
RUN pipenv install --dev

# Create .po and .mo translation files
WORKDIR /code/polaris/polaris
RUN pipenv run django-admin compilemessages
WORKDIR /code/server
RUN pipenv run django-admin compilemessages

WORKDIR /code
CMD run.sh