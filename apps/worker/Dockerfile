FROM python:3.12-slim

WORKDIR /app

COPY apps/worker/pyproject.toml ./
COPY apps/worker/app/ app/
COPY apps/api/app/domain/ranking.py apps/api/app/domain/ranking.py
COPY apps/api/app/domain/rules.py apps/api/app/domain/rules.py

RUN pip install --no-cache-dir . \
    && useradd -m -u 10001 app \
    && chown -R app:app /app

USER app
CMD ["python", "-m", "app.main"]
