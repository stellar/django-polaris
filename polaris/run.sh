pipenv run python manage.py migrate
pipenv run python manage compilescss
pipenv run python manage.py collectstatic --no-input -v 0
pipenv run python manage.py runsslserver --nostatic --certificate cert.pem --key key.pem 0.0.0.0:8000
