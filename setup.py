from setuptools import setup, find_packages


with open("README.rst") as f:
    long_description = f.read()

setup(
    name="django-polaris",
    version="1.5.0",
    description="An extendable Django server for Stellar Ecosystem Proposals",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://django-polaris.readthedocs.io/en/stable",
    author="Jake Urban",
    author_email="jake@stellar.org",
    license="Apache license 2.0",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 2.2",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.7",
    ],
    keywords=[
        "stellar",
        "sdf",
        "anchor",
        "server",
        "polaris",
        "sep-24",
        "sep24",
        "sep-31",
        "sep31",
    ],
    include_package_data=True,
    package_dir={"": "polaris"},
    packages=find_packages("polaris"),
    install_requires=[
        "aiohttp==3.7.4.post0; python_version >= '3.6'",
        "aiohttp-sse-client==0.2.1",
        "asgiref==3.4.1; python_version >= '3.6'",
        "async-timeout==3.0.1; python_full_version >= '3.5.3'",
        "attrs==21.2.0; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4'",
        "certifi==2021.5.30",
        "cffi==1.14.6",
        "chardet==4.0.0; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4'",
        "charset-normalizer==2.0.3; python_version >= '3'",
        "cryptography==3.4.7",
        "django==3.2.6",
        "django-cors-headers==3.7.0",
        "django-environ==0.4.5",
        "django-model-utils==4.1.1",
        "djangorestframework==3.12.4",
        "idna==3.2; python_version >= '3'",
        "mnemonic==0.19",
        "multidict==5.1.0; python_version >= '3.6'",
        "psycopg2-binary==2.9.1",
        "pycparser==2.20; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
        "pyjwt==1.7.1",
        "pynacl==1.4.0; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
        "pytz==2021.1",
        "requests==2.26.0; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4, 3.5'",
        "six==1.16.0; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3'",
        "sqlparse==0.4.1; python_version >= '3.5'",
        "stellar-base-sseclient==0.0.21",
        "stellar-sdk==4.1.0",
        "toml==0.10.2",
        "typing-extensions==3.10.0.0; python_version < '3.8'",
        "urllib3==1.26.6; python_version >= '2.7' and python_version not in '3.0, 3.1, 3.2, 3.3, 3.4' and python_version < '4'",
        "whitenoise==5.3.0",
        "yarl==1.6.3; python_version >= '3.6'",
    ],
    python_requires=">=3.7",
)
