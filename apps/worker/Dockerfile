FROM python:3.12-slim

WORKDIR /app

COPY apps/worker/pyproject.toml ./
COPY apps/worker/app/ app/
COPY apps/api/app/domain/ranking.py apps/api/app/domain/ranking.py

RUN pip install --no-cache-dir .

CMD ["python", "-m", "app.main"]
