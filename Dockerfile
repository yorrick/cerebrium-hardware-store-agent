# syntax=docker/dockerfile:1

# Use the official UV Python base image with Python 3.11 on Debian Bookworm
# UV is a fast Python package manager that provides better performance than pip
ARG PYTHON_VERSION=3.11
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Set HF_HOME for model caching (Cerebrium requirement)
ENV HF_HOME=/cortex/.cache/

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install build dependencies required for Python packages with native extensions
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Create a new directory for our application code
WORKDIR /app

# Create the cache directory for model files
RUN mkdir -p /cortex/.cache && chown -R appuser:appuser /cortex

# Copy just the dependency files first, for more efficient layer caching
COPY pyproject.toml ./
RUN mkdir -p src

# Install Python dependencies
# Note: We don't use --locked since we might not have a uv.lock file
RUN uv sync

# Copy all remaining application files into the container
COPY . .

# Change ownership of all app files to the non-privileged user
RUN chown -R appuser:appuser /app

# Switch to the non-privileged user for all subsequent operations
USER appuser

# Pre-download any ML models or files the agent needs
# This ensures the container is ready to run immediately
RUN uv run src/agent.py download-files

# Expose the port for Cerebrium
EXPOSE 8600

# Run the application using UV
# The "start" command tells the worker to connect to LiveKit and begin waiting for jobs.
CMD ["uv", "run", "src/agent.py", "start"]
