FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY bot ./bot
COPY knowledge.md ./
RUN uv sync --frozen --no-dev
CMD ["uv", "run", "--no-sync", "python", "-m", "bot.main"]
