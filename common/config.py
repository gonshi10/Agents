"""Centralized environment configuration for all agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    finnhub_api_key: str
    openai_api_key: str | None
    openai_model: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    email_to: str
    watchlist_csv: str
    test_mode: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    finnhub_api_key = os.getenv("FINNHUB_API_KEY")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_to = os.getenv("EMAIL_TO")

    required = {
        "FINNHUB_API_KEY": finnhub_api_key,
        "SMTP_USER": smtp_user,
        "SMTP_PASS": smtp_pass,
        "EMAIL_TO": email_to,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return Settings(
        finnhub_api_key=finnhub_api_key or "",
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=smtp_user or "",
        smtp_pass=smtp_pass or "",
        email_to=email_to or "",
        watchlist_csv=os.getenv("WATCHLIST_CSV", "./agents/earnings_agent/data/watchlist.csv"),
        test_mode=_as_bool(os.getenv("TEST_MODE"), default=False),
    )

