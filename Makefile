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

tag:
	git tag -a ${PROJECT_VERSION} -m "new tag"
	git push --tags


pypi: tag
	python setup.py sdist
	twine check dist/*
	twine upload dist/*