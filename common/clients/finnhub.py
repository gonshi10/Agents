"""Finnhub client with centralized rate limiting and helpers."""

from __future__ import annotations

import time
from typing import Any

import requests


class FinnhubClient:
    def __init__(self, api_key: str, max_calls_per_minute: int = 50):
        self.api_key = api_key
        self.max_calls_per_minute = max_calls_per_minute
        self.call_count = 0
        self.last_reset_time = time.time()
        self.session = requests.Session()

    def _check_rate_limit(self) -> None:
        current_time = time.time()

        if current_time - self.last_reset_time >= 60:
            self.call_count = 0
            self.last_reset_time = current_time

        if self.call_count >= self.max_calls_per_minute:
            wait_time = 60 - (current_time - self.last_reset_time) + 1
            print(f"⏳ Finnhub rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.call_count = 0
            self.last_reset_time = time.time()
            print("✅ Finnhub rate limit window reset")

        self.call_count += 1

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        self._check_rate_limit()
        response = self.session.get(
            f"https://finnhub.io/api/v1/{endpoint}",
            params={"token": self.api_key, **params},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_earnings_calendar(self, ticker: str, date_str: str) -> dict[str, Any] | None:
        try:
            data = self._get(
                "calendar/earnings",
                {"from": date_str, "to": date_str, "symbol": ticker},
            )
            earnings = data.get("earningsCalendar", [])
            return earnings[0] if earnings else None
        except Exception as exc:
            print(f"✗ Failed to fetch earnings for {ticker}: {exc}")
            return None

    def get_company_news(self, ticker: str, date_str: str) -> list[dict[str, Any]]:
        try:
            news = self._get(
                "company-news",
                {"symbol": ticker, "from": date_str, "to": date_str},
            )
            if not isinstance(news, list):
                return []

            relevant_news: list[dict[str, Any]] = []
            for item in news:
                headline = str(item.get("headline", "")).lower()
                if any(
                    keyword in headline
                    for keyword in [
                        "earnings",
                        "quarterly",
                        "results",
                        "guidance",
                        "outlook",
                        "forecast",
                        "investor",
                        "conference",
                        "call",
                        "press release",
                        "strategic",
                        "initiative",
                        "expansion",
                        "acquisition",
                        "partnership",
                        "restructuring",
                        "cost cutting",
                    ]
                ):
                    relevant_news.append(item)
            return relevant_news[:5]
        except Exception as exc:
            print(f"✗ Failed to fetch news for {ticker}: {exc}")
            return []

    def get_stock_profile(self, ticker: str) -> dict[str, Any]:
        try:
            data = self._get("stock/profile2", {"symbol": ticker})
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"⚠️ Failed to fetch stock profile for {ticker}: {exc}")
            return {}

