"""Watchlist loading helpers."""

from __future__ import annotations

import csv


def load_tickers(csv_file: str) -> list[str]:
    tickers: list[str] = []
    try:
        with open(csv_file, "r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = str(row.get("Symbol", "")).strip().upper()
                if symbol:
                    tickers.append(symbol)
    except Exception as exc:
        print(f"✗ Failed to load tickers from {csv_file}: {exc}")
        return []

    print(
        f"✓ Loaded {len(tickers)} tickers: "
        f"{', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}"
    )
    return tickers

