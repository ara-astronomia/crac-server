FROM python:3.12-slim-bookworm

# git required for the crac-protobuf git dependency
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Step 1 - install dependencies only (cached layer, unaffected by source changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Step 2 - copy source and install the package
COPY crac_server ./crac_server
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 50051

CMD ["python", "-m", "crac_server.app"]
