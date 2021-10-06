from setuptools import setup, find_packages


with open("README.rst") as f:
    long_description = f.read()

setup(
    name="django-polaris",
    version="1.6.3",
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
        "django<3.0",
        "django-environ",
        "django-model-utils",
        "djangorestframework",
        "whitenoise",
        "psycopg2-binary<2.9",
        "stellar-sdk~=2.13",
        "django-cors-headers",
        "toml",
        "pyjwt==1.7.1",
        "cryptography",
    ],
    python_requires=">=3.7",
)
