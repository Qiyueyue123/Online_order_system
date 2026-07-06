FROM python:3.12-slim AS runtime
WORKDIR /app
COPY pyproject.toml .
COPY app app
RUN pip install --no-cache-dir .
COPY alembic.ini .
COPY migrations migrations
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
