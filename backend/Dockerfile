FROM python:3.12

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml .
# Install dependencies using uv
RUN uv pip install --system --no-cache -e ".[dev]"

COPY . .
