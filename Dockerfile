FROM python:3.7.7-slim-stretch

# File Author / Maintainer
MAINTAINER Thomas Schmelzer "thomas.schmelzer@gmail.com"

COPY . /tmp/eikon

RUN buildDeps='gcc g++' && \
    apt-get update && apt-get install -y $buildDeps --no-install-recommends && \
    pip install --no-cache-dir /tmp/eikon && \
    rm -r /tmp/eikon && \
    apt-get purge -y --auto-remove $buildDeps
