release: pipenv run python src/manage.py migrate
web: gunicorn --pythonpath src app.wsgi
