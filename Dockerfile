# syntax=docker/dockerfile:1.16
FROM python:3.12-slim AS eikon

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:0.7.8 /uv /bin/uv

# Set environment variables in one layer
# Combining multiple ENV commands into one reduces the number of layers in the final image
ENV UV_SYSTEM_PYTHON=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

 # Explanation of environment variables:
# - UV_SYSTEM_PYTHON=1: Tells uv to use the system Python instead of creating a virtual environment
# - PYTHONUNBUFFERED=1: Prevents Python from buffering stdout/stderr (better for logging in containers)
# - PYTHONDONTWRITEBYTECODE=1: Prevents Python from writing .pyc files (reduces image size)
# - PIP_NO_CACHE_DIR=1: Prevents pip from using a cache directory (reduces image size)

# Create non-root user and chown the app directory
# Running as a non-root user is a security best practice for containers
# - useradd -m: Creates a user with a home directory
# - -u 1000: Sets the user ID to 1000 (standard for first non-root user)
# - mkdir /app: Creates the application directory
# - chown user:user /app: Gives the new user ownership of the app directory
RUN useradd -m -u 1000 user && mkdir /app && chown user:user /app

WORKDIR /app

# Copy and install dependencies first for better caching
COPY --chown=user:user requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Switch to non-root user
# This is a security best practice to limit the potential damage if the container is compromised
USER user

# Add healthcheck
# This allows Docker to monitor the health of the container
# Parameters:
# - interval=30s: Check every 30 seconds
# - timeout=30s: Allow 30 seconds for the check to complete
# - start-period=5s: Give 5 seconds grace period on startup
# - retries=3: Fail after 3 consecutive failed checks
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1


#FROM python:3.7.7-slim-stretch as eikon

#COPY . /tmp/eikon

#RUN pip install --no-cache-dir /tmp/eikon && \
#    rm -r /tmp/eikon

#### Here the test-configuration
FROM eikon AS test

USER root

COPY --chown=user:user ./tests /app/tests

RUN uv pip install --no-cache-dir -r /app/tests/requirements.txt

USER user
