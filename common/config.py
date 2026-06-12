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
    ratings_pt_snapshot: str
    flights_api_token: str | None
    flights_watchlist_csv: str
    flights_price_snapshot: str
    flights_price_drop_pct: float
    flights_currency: str
    adzuna_app_id: str | None
    adzuna_app_key: str | None
    techstack_watchlist_csv: str
    techstack_snapshot: str
    techstack_trend_threshold: float
    techstack_lookback_days: int
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
        watchlist_csv=os.getenv("WATCHLIST_CSV", "./common/data/watchlist.csv"),
        ratings_pt_snapshot=os.getenv(
            "RATINGS_PT_SNAPSHOT", "./agents/ratings_agent/data/price_targets.snapshot.json"
        ),
        # Flights agent. FLIGHTS_API_TOKEN is intentionally optional here (not in the
        # required set above) so earnings/ratings runs don't break when it is unset;
        # FlightsAgent validates its presence and degrades gracefully.
        flights_api_token=os.getenv("FLIGHTS_API_TOKEN"),
        flights_watchlist_csv=os.getenv(
            "FLIGHTS_WATCHLIST_CSV", "./agents/flights_agent/data/routes.csv"
        ),
        flights_price_snapshot=os.getenv(
            "FLIGHTS_PRICE_SNAPSHOT", "./agents/flights_agent/data/prices.snapshot.json"
        ),
        flights_price_drop_pct=float(os.getenv("FLIGHTS_PRICE_DROP_PCT", "10")),
        flights_currency=os.getenv("FLIGHTS_CURRENCY", "usd"),
        # Techstack agent. Adzuna credentials are optional so other agents are unaffected.
        adzuna_app_id=os.getenv("ADZUNA_APP_ID"),
        adzuna_app_key=os.getenv("ADZUNA_APP_KEY"),
        techstack_watchlist_csv=os.getenv(
            "TECHSTACK_WATCHLIST_CSV", "./agents/techstack_agent/data/companies.csv"
        ),
        techstack_snapshot=os.getenv(
            "TECHSTACK_SNAPSHOT", "./agents/techstack_agent/data/tech_mentions.snapshot.json"
        ),
        techstack_trend_threshold=float(os.getenv("TECHSTACK_TREND_THRESHOLD", "20")),
        techstack_lookback_days=int(os.getenv("TECHSTACK_LOOKBACK_DAYS", "30")),
        test_mode=_as_bool(os.getenv("TEST_MODE"), default=False),
    )

