FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN useradd --create-home rackops && mkdir -p /app/data && chown -R rackops /app/data
USER rackops
EXPOSE 8000
# Migrate, seed (no-op when already seeded), then serve. Binds 0.0.0.0 inside the container only;
# docker-compose publishes it on 127.0.0.1.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
