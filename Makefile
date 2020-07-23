#!make

#include eikon/__init__.py
PROJECT_VERSION := 1.1.2
PACKAGE := EIKON

.PHONY: help build test tag clean

.DEFAULT: help

help:
	@echo "make test"
	@echo "       Build the docker image for testing and run them."
	@echo "make tag"
	@echo "       Make a tag on Github."


build:
	docker-compose build eikon

test:
	docker-compose -f docker-compose.test.yml run sut

tag: test
	git tag -a ${PROJECT_VERSION} -m "new tag"
	git push --tags

test:
	docker-compose -f docker-compose.test.yml run sut
