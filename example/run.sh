# Apply new migrations
pipenv run python manage.py migrate
# Compile SCSS
pipenv run python manage.py compilescss
# Create compiled static assets
pipenv run python manage.py collectstatic --no-input -v 0
# Run SSL server
pipenv run python manage.py runsslserver --nostatic --certificate cert.pem --key key.pem 0.0.0.0:8000
