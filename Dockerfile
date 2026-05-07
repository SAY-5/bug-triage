FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-root --only main

COPY src /app/src
COPY corpus /app/corpus
COPY alembic.ini /app/
COPY alembic /app/alembic
RUN poetry install --only-root

EXPOSE 8000

CMD ["uvicorn", "bug_triage.api:app", "--host", "0.0.0.0", "--port", "8000"]
