FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY src/ src/
COPY sql/ sql/

ENV PYTHONPATH=/app/src

CMD ["python", "src/main.py"]
