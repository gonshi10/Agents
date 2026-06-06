"""Adzuna jobs API client with centralized rate limiting."""

from __future__ import annotations

import time
from typing import Any

import requests


class AdzunaClient:
    """Simple wrapper around Adzuna search API.

    Docs: https://developer.adzuna.com/overview
    """

    def __init__(
        self,
        app_id: str,
        app_key: str,
        country: str = "us",
        max_calls_per_minute: int = 50,
    ):
        self.app_id = app_id
        self.app_key = app_key
        self.country = country
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
            print(f"⏳ Adzuna rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.call_count = 0
            self.last_reset_time = time.time()
            print("✅ Adzuna rate limit window reset")

        self.call_count += 1

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        self._check_rate_limit()
        response = self.session.get(
            f"https://api.adzuna.com/v1/api/jobs/{self.country}/{endpoint}",
            params={"app_id": self.app_id, "app_key": self.app_key, **params},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def get_job_postings(self, query: str, max_days_old: int = 7) -> list[dict[str, Any]]:
        """Fetch recent postings for a query.

        Returns normalized entries with `title`, `description`, `company`.
        """
        results: list[dict[str, Any]] = []
        try:
            for page in (1, 2):
                payload = self._get(
                    f"search/{page}",
                    {
                        "what": query,
                        "results_per_page": 50,
                        "max_days_old": max_days_old,
                        "sort_by": "date",
                        "content-type": "application/json",
                    },
                )
                batch = payload.get("results", [])
                if not isinstance(batch, list) or not batch:
                    break
                for item in batch:
                    if not isinstance(item, dict):
                        continue
                    results.append(
                        {
                            "title": str(item.get("title", "")),
                            "description": str(item.get("description", "")),
                            "company": str((item.get("company") or {}).get("display_name", "")),
                            "created": str(item.get("created", "")),
                            "location": str((item.get("location") or {}).get("display_name", "")),
                        }
                    )
            return results
        except Exception as exc:
            print(f"⚠️ Failed to fetch job postings for query '{query}': {exc}")
            return []

