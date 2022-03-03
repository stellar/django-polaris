from setuptools import setup, find_packages


with open("README.rst") as f:
    long_description = f.read()

setup(
    name="django-polaris",
    version="2.2.0",
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
        "Framework :: Django :: 3.2",
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
        "django>=3.2,<4.0",
        "asgiref>=3.2,<4",
        "django-environ",
        "django-model-utils<5.0,>=4.1",
        "djangorestframework>=3.12,<4.0",
        "whitenoise>=5.3,<6.0",
        "stellar-sdk>=6.0.1,<7.0.0",
        "aiohttp>=3.7,<4",
        "django-cors-headers>=3.7,<4.0",
        "toml",
        "pyjwt<3.0,>=2.1",
        "cryptography>=3.4,<4.0",
        "sqlparse>=0.4.2",
    ],
    python_requires=">=3.7",
)
