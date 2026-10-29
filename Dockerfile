FROM python:3.15-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY pyproject.toml uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.12.1,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-cache && useradd --uid 10001 --create-home app
COPY analytics.py app.py report.py generator.py investigation.py ./
COPY static/ ./static/
USER app
EXPOSE 8080
CMD ["/app/.venv/bin/uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
