"""OpenAI wrapper with rate limiting and fallback support."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from openai import OpenAI

T = TypeVar("T")


class OpenAIClient:
    def __init__(self, api_key: str | None, model: str, calls_per_minute: int = 3):
        self.model = model
        self.calls_per_minute = calls_per_minute
        self.call_times: list[float] = []
        self.client = OpenAI(api_key=api_key) if api_key else None

    @property
    def is_enabled(self) -> bool:
        return self.client is not None

    def _wait_for_rate_limit(self) -> None:
        now = time.time()
        self.call_times = [t for t in self.call_times if now - t < 60]
        if len(self.call_times) >= self.calls_per_minute:
            wait_time = 60 - (now - self.call_times[0]) + 2
            print(f"⏳ OpenAI rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            now = time.time()
        self.call_times.append(now)

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        if not self.client:
            raise RuntimeError("OpenAI client is not configured")

        self._wait_for_rate_limit()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def run_with_fallback(self, primary: Callable[[], T], fallback: Callable[[], T]) -> T:
        try:
            return primary()
        except Exception as exc:
            print(f"⚠️ OpenAI primary path failed, using fallback: {exc}")
            return fallback()

