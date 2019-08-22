release: pipenv run python src/manage.py migrate
worker: celery worker --app app --beat --workdir src -l info
web: gunicorn --pythonpath src app.wsgi
