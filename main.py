"""Project entry point.

Starts the FastAPI backend via uvicorn. Run with::

    python main.py

Or directly::

    uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001
"""

import uvicorn

from backend.core.config import settings


def main() -> None:
    """Start the uvicorn server using settings from the environment."""
    uvicorn.run(
        "backend.app:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
        log_config=None,  # structlog handles logging
    )


if __name__ == "__main__":
    main()
