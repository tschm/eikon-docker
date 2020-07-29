FROM python:3.7.7-slim-stretch as eikon

# File Author / Maintainer
MAINTAINER Thomas Schmelzer "thomas.schmelzer@gmail.com"

COPY . /tmp/eikon

RUN pip install --no-cache-dir /tmp/eikon && \
    rm -r /tmp/eikon


#### Here the test-configuration
FROM eikon as test

RUN pip install --no-cache-dir pytest pytest-cov pytest-html sphinx requests-mock

WORKDIR /eikon

CMD py.test --cov=eikon  -vv --cov-report html:artifacts/html-coverage --cov-report term --html=artifacts/html-report/report.html test
