"""Entrypoint for techstack agent package."""

from __future__ import annotations

import sys

from common.config import get_settings

from .agent import TechstackAgent


def main() -> None:
    try:
        settings = get_settings()
        agent = TechstackAgent(settings)
        agent.run(test_mode=settings.test_mode)
    except Exception as exc:
        print(f"❌ Fatal error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

