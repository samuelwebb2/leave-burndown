"""Annual leave burn-down. The leave year runs 1 Sep to 31 Aug."""

import os

from .web import create_app

__all__ = ["create_app", "main"]


def main() -> None:
    """Run the development server. Debug mode is opt-in via LEAVE_DEBUG=1."""
    debug = os.environ.get("LEAVE_DEBUG", "").lower() in {"1", "true", "yes"}
    create_app().run(host="127.0.0.1", port=5050, debug=debug)
