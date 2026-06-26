FROM python:3.14-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-install-project --no-editable

# Copy application code
COPY . .

# Sync again with the project
RUN uv sync --frozen --no-editable


FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=builder --chown=user:user /app /app

EXPOSE 80

CMD ["fastapi", "run", "src/main.py", "--port", "80", "--proxy-headers"]
