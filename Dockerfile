FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy

WORKDIR /app

# Dependency layer — cached unless pyproject.toml or uv.lock change
COPY pyproject.toml uv.lock ./
# GIT_SSL_NO_VERIFY only for this step: crac-protobuf is a public repo fetched over HTTPS
# and Docker's git may lack the required intermediate CA depending on the host environment.
RUN GIT_SSL_NO_VERIFY=1 uv sync --extra dev --no-install-project --frozen

# Project source
COPY . .
RUN uv sync --extra dev --frozen

CMD ["uv", "run", "coverage", "run", "run_tests.py"]
