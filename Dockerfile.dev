# Python version
FROM python:3.7-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update && apk add build-base postgresql-dev libffi-dev

# Copy files to working directory
RUN mkdir /code
COPY ./polaris /code/
RUN mkdir /code/server
COPY ./example/server /code/server/
COPY ./Pipfile ./Pipfile.lock /code/

# Install dependencies
WORKDIR /code
RUN pip install pipenv
RUN pipenv lock --clear
RUN pipenv install --dev

CMD run.sh