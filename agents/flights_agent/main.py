"""Entrypoint for flights agent package."""

from __future__ import annotations

import sys

from common.config import get_settings

from .agent import FlightsAgent


def main() -> None:
    try:
        settings = get_settings()
        agent = FlightsAgent(settings)
        agent.run(test_mode=settings.test_mode)
    except Exception as exc:
        print(f"❌ Fatal error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
