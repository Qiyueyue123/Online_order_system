FROM python:3.14-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
COPY app app
RUN pip install --no-cache-dir .
COPY alembic.ini .
COPY migrations migrations
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
