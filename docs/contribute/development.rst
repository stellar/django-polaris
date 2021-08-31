# How to set up Polaris local development environment with PyCharm

If you would like to contribute to Polaris, this document will guide you to set up your development environment on
Ubuntu systems.

## Install Python 3.7

Polaris uses Python3.7. It is important that you have Python3.7 installed correctly. However, Ubuntu 20.04LTS comes
with Python3.8.x. In this document, we will guide you to set up your environment with both 3.7 and 3.8 as alternatives.

Run the following commands to install 3.7

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.7
```

Check your version with

```bash
/usr/bin/python3.7 --version
```

You should be able to see something like `Python3.7.x`.

### Switch between Python versions

To switch between python version, we can use `update-alternatives` command.

This command will add Python3.7 to the alternatives as priority #1
```bash
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.7 1
```

To switch between versions, run the following command
```bash
sudo update-alternatives --config python
```

This should give you a response like the following. Then choose the number.

```
here are 2 choices for the alternative python (providing /usr/bin/python).

  Selection    Path                Priority   Status
------------------------------------------------------------
  0            /usr/bin/python3.8   2         auto mode
* 1            /usr/bin/python3.7   1         manual mode
  2            /usr/bin/python3.8   2         manual mode

Press <enter> to keep the current choice[*], or type selection number:
```




Check your result by `python --version`.

## Install `pip` and `pipenv`

To install `pip`, run the following command.

```bash
sudo apt install python3-pip
```

Check the version by `pip --version`. This should give you something like:

```bash
pip 20.0.2 from /usr/lib/python3/dist-packages/pip (python 3.8)
```

To install `pipenv`, run the following command.

``` bash
sudo pip install pipenv
```

## Install `libpython3.7-dev`
`django-polaris` requires `rcssmin` package, which requires compilation and building from the source code. It is 
necessary to install `libpython3.7-dev` package in order for `pipenv install` to succeed.

```bash
sudo apt install libpython3.7-dev
```

## Modify `Pipfile` to enable local development
Replace the `[packages]` section as the following:
```
[packages]
gunicorn = "*"
psycopg2-binary = ">=2.9, <3.0"

# Uncomment the following line if you would like to run the dev without docker
django-polaris = {path = "..", editable = true}

# Comment the following line if you would like to run the dev without docker
# django-polaris = {path = "/code", editable = true}
```

## Install packages in virtualenv
Run the following command to create virtualenv and install required packages.

```
cd $HOME/django-polaris/example
rm Pipfile.lock
pipenv install --dev
```
You should be able to see all package requirements installed.

### Configure `.env` file
The Polaris reference server requires correct configurations of ``$HOME/django-polaris/example/.env` to run correctly.
Please create with the following example. You will need to obtain the following information before you can correctly
run the server.

- SIGNING_SEED
- MULT_ASSET_ADDITIONAL_SIGNING_SEED

These secrets can be obtained from the SDF team.

```
DJANGO_SECRET_KEY="secretkeykeysecret"
DJANGO_DEBUG=True

ACTIVE_SEPS="sep-1,sep-6,sep-10,sep-12,sep-24,sep-31"
SIGNING_SEED="Sxxx..."

# "Test SDF Network ; September 2015" or "Public Global Stellar Network ; September 2015"
# Or a custom passphrase if you're using a private network.
STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"

MULT_ASSET_ADDITIONAL_SIGNING_SEED="Sxxx..."

HORIZON_URI="https://horizon-testnet.stellar.org/"
SERVER_JWT_KEY="secret"
DJANGO_ALLOWED_HOSTS=stellar-anchor-server.herokuapp.com,localhost,0.0.0.0,127.0.0.1
HOST_URL="http://localhost:8000"
LOCAL_MODE=True
ADDITIVE_FEES_ENABLED=True

EMAIL_HOST_USER="sdf.reference.anchor.server@gmail.com"
EMAIL_HOST_PASSWORD="stellarpassword1"
```

## Add the assets to database
Follow this [instruction](https://github.com/stellar/django-polaris/blob/master/docs/tutorials/index.rst#add-the-asset-to-the-database)
to add assets. Be sure to have the following information ready before you use the instruction.

- asset_issuer_public_key: `"Gxxxx...."`
- asset_distribution_account_secret_key: `"Sxxx...."`

Verify by running the server as the following commands
```bash
cd $HOME/django-polaris/example
python manage.py runserver
```

## Pycharm Integration

### Clone and open `django-polaris`
Follow the instruction from Jetbrains: [Configure a Pipenv environment](https://www.jetbrains.com/help/pycharm/pipenv.html)

Clone `django-polaris` from Github.
```bash
cd
git clone git@github.com:stellar/django-polaris.git
```

Start PyCharm and open `django-polaris` as a project. 

### Configure `pipenv` environment
- Open `File->Settings`
- Find and click `Project: -> Python Interpreter`
- Under `Python Interpreter`, click on the gear button at the right and select `"Add"`
- Select `Pipenv Environment` on the left pane. Make sure `/usr/bin/python3.7` is selected as `Base Interpreter`.
- Make sure `Install packages from Pipfile` is checked

This should start installing all Python packages.

### Add Run Configuration
In order to debug with PyCharm, we should add a Run Configuration.
- At the top right of PyCharm, click on the `Add Configuration` drop-down list.
- Click on `Add New` and select `Django Server`. This will create a Django Server run configuration.
- In the `Name` field, enter `Polaris Reference Server`
- In the `Host` field, enter `localhost`
- Click on `OK` to continue.

You should be able to run and debug the Polaris Reference Server in PyCharm.
