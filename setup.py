#!/usr/bin/env python

from setuptools import find_packages, setup

# read the contents of your README file
with open("README.md") as f:
    long_description = f.read()

setup(
    name="eikon-docker",
    long_description=long_description,
    long_description_content_type="text/markdown",
    version="0.0.1",
    packages=find_packages(include=["eikon*"]),
    author="Thomas Schmelzer",
    author_email="thomas.schmelzer@gmail.com",
    url="https://github.com/tschm/eikon-docker",
    description="Use the Python Eikon Data API from within a container",
    install_requires=[
        "requests==2.31.0",
        "appdirs==1.4.3",
        "requests-async==0.6.2",
        "websocket-client",
        "deprecation",
        "nest-asyncio==1.0.0",
        "pandas",
    ],
    license="Apache 2.0",
)
