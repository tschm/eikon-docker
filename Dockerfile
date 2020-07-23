FROM python:3.7.7-slim-stretch as builder

# File Author / Maintainer
MAINTAINER Thomas Schmelzer "thomas.schmelzer@gmail.com"

COPY . /tmp/eikon

RUN buildDeps='gcc g++' && \
    apt-get update && apt-get install -y $buildDeps --no-install-recommends && \
    pip install --no-cache-dir /tmp/eikon && \
    rm -r /tmp/eikon && \
    apt-get purge -y --auto-remove $buildDeps


#### Here the test-configuration
FROM builder as test

RUN pip install --no-cache-dir httpretty pytest pytest-cov pytest-html sphinx requests-mock

WORKDIR /eikon

CMD py.test --cov=eikon  -vv --cov-report html:artifacts/html-coverage --cov-report term --html=artifacts/html-report/report.html /eikon/test
