release: pipenv run python src/manage.py migrate
worker: celery worker --app app --beat --workdir src -l info
watcher: pipenv run python src/manage.py watch_transactions
web: gunicorn --pythonpath src app.wsgi
