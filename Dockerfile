FROM python:3.7.7-slim-stretch as eikon

COPY . /tmp/eikon

RUN pip install --no-cache-dir /tmp/eikon && \
    rm -r /tmp/eikon

#### Here the test-configuration
FROM eikon as test

COPY ./test /eikon/test

RUN pip install --no-cache-dir -r /eikon/test/requirements.txt

WORKDIR /eikon
