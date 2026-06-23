import os

from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue


def normalize_database_url(database_url: str | None) -> str | None:
    if database_url is None:
        return None
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    return database_url


def create_worker_queue() -> InMemoryJobQueue | PostgresJobQueue:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if database_url:
        return PostgresJobQueue(database_url)
    return InMemoryJobQueue()
