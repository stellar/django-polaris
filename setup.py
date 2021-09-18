from setuptools import setup, find_packages


with open("README.rst") as f:
    long_description = f.read()

setup(
    name="django-polaris",
    version="2.0.0",
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
        "django-model-utils>=4.1,<5.0",
        "djangorestframework>=3.12,<4.0",
        "whitenoise<6.0,>=5.3",
        "stellar-sdk>=4.2.1,<5.0",
        "aiohttp<4,>=3.7",
        "django-cors-headers<4.0,>=3.7",
        "toml",
        "pyjwt>=2.1,<3.0",
        "cryptography<4.0,>=3.4",
        "sqlparse>=0.4.2",
    ],
    python_requires=">=3.7",
)
