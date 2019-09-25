# Python version
FROM python:3.7-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update && apk add build-base postgresql-dev

# Copy files to working directory
RUN mkdir /code
COPY . /code/

# Install dependencies
WORKDIR /code
RUN pip install pipenv
RUN pipenv update
RUN pipenv install

CMD ["pipenv", "run", "python", "src/manage.py", "runserver", "0.0.0.0:8000"]
