from __future__ import annotations

from app.core.tasks import get_celery


if __name__ == "__main__":
    get_celery().start()


