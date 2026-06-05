"""Travelpayouts (Aviasales) flight-price client with rate limiting.

Wraps the free Aviasales Data API ``prices_for_dates`` endpoint, which returns
the cheapest fares Aviasales users found in the last 48h for a route/month.
Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163-Aviasales-Data-API
"""

from __future__ import annotations

import time
from typing import Any

import requests

API_BASE = "https://api.travelpayouts.com"
AVIASALES_WEB = "https://www.aviasales.com"


class TravelpayoutsClient:
    def __init__(self, token: str, max_calls_per_minute: int = 50):
        self.token = token
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
            print(f"⏳ Travelpayouts rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.call_count = 0
            self.last_reset_time = time.time()
            print("✅ Travelpayouts rate limit window reset")

        self.call_count += 1

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        self._check_rate_limit()
        response = self.session.get(
            f"{API_BASE}/{endpoint}",
            params={"token": self.token, **params},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_cheapest_fare(
        self,
        origin: str,
        destination: str,
        depart_month: str,
        return_month: str | None = None,
        one_way: bool = False,
        currency: str = "usd",
    ) -> dict[str, Any] | None:
        """Return the single cheapest fare for a route, or None.

        ``depart_month`` / ``return_month`` accept YYYY-MM (whole-month cheapest)
        or YYYY-MM-DD. The returned ``link`` is normalized to an absolute URL.
        """
        params: dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "departure_at": depart_month,
            "currency": currency,
            "sorting": "price",
            "direct": "false",
            "one_way": "true" if one_way else "false",
            "limit": 1,
            "page": 1,
        }
        if return_month and not one_way:
            params["return_at"] = return_month

        try:
            payload = self._get("aviasales/v3/prices_for_dates", params)
            if not isinstance(payload, dict) or not payload.get("success"):
                return None
            data = payload.get("data") or []
            if not data:
                return None
            record = data[0]
            price = record.get("price")
            if price in (None, 0, "0"):
                return None
            link = record.get("link") or ""
            if link and link.startswith("/"):
                link = f"{AVIASALES_WEB}{link}"
            return {
                "price": float(price),
                "airline": str(record.get("airline", "")),
                "departure_at": str(record.get("departure_at", "")),
                "return_at": str(record.get("return_at", "")),
                "link": link,
            }
        except Exception as exc:
            print(f"⚠️ Failed to fetch fare for {origin}→{destination} {depart_month}: {exc}")
            return None
