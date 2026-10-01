FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/backend

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


# Test/dev image: runtime deps + test deps, so `docker compose --profile test up test`
# needs no network at run time.
FROM base AS dev
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
