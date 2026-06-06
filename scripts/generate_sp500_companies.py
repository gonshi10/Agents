#!/usr/bin/env python3
"""Merge top-200 S&P 500 companies into techstack companies.csv.

Preserves existing rows, appends new S&P 500 rows ranked by market cap, and
deduplicates by ticker/name.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

import requests

CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
)
FINANCIALS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies-financials/master/data/"
    "constituents-financials.csv"
)
TARGET_COUNT = 200
ROOT = Path(__file__).resolve().parents[1]
COMPANIES_CSV = ROOT / "agents" / "techstack_agent" / "data" / "companies.csv"


def normalize_company_name(name: str) -> str:
    cleaned = name.lower().strip()
    cleaned = re.sub(r"\b(incorporated|inc|corp|corporation|plc|ltd|llc|co)\.?\b", "", cleaned)
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def clean_search_name(name: str) -> str:
    cleaned = re.sub(r"\b(Inc\.?|Corporation|Corp\.?|PLC|Ltd\.?|LLC)\b", "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned or name


def load_existing_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "Company": str(row.get("Company", "")).strip(),
                    "Ticker": str(row.get("Ticker", "")).strip().upper(),
                    "SearchQuery": str(row.get("SearchQuery", "")).strip(),
                    "Sector": str(row.get("Sector", "")).strip(),
                }
            )
    return rows


def fetch_constituents() -> list[dict[str, str]]:
    response = requests.get(CONSTITUENTS_URL, timeout=20)
    response.raise_for_status()
    reader = csv.DictReader(response.text.splitlines())
    results: list[dict[str, str]] = []
    for row in reader:
        symbol = str(row.get("Symbol", "")).strip().upper()
        security = str(row.get("Security", "")).strip()
        gics_sector = str(row.get("GICS Sector", "")).strip()
        if symbol and security:
            results.append({"Symbol": symbol, "Security": security, "GICSSector": gics_sector})
    return results


def parse_market_cap(value: str) -> float:
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return 0.0
    multiplier = 1.0
    suffix = cleaned[-1].upper()
    if suffix == "T":
        multiplier = 1_000_000_000_000.0
        cleaned = cleaned[:-1]
    elif suffix == "B":
        multiplier = 1_000_000_000.0
        cleaned = cleaned[:-1]
    elif suffix == "M":
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


def fetch_financial_caps() -> dict[str, float]:
    response = requests.get(FINANCIALS_URL, timeout=20)
    response.raise_for_status()
    reader = csv.DictReader(response.text.splitlines())
    caps: dict[str, float] = {}
    for row in reader:
        symbol = str(row.get("Symbol", "")).strip().upper()
        market_cap = parse_market_cap(str(row.get("Market Cap", "")).strip())
        if symbol and market_cap > 0:
            caps[symbol] = market_cap
    return caps


def enrich_and_rank(constituents: list[dict[str, str]], market_caps: dict[str, float]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in constituents:
        symbol = item["Symbol"]
        market_cap = float(market_caps.get(symbol, 0.0))
        if market_cap <= 0:
            continue

        ranked.append(
            {
                "Symbol": symbol,
                "Company": str(item["Security"]).strip(),
                "Sector": str(item["GICSSector"]).strip(),
                "MarketCap": market_cap,
            }
        )

    ranked.sort(key=lambda row: row["MarketCap"], reverse=True)
    return ranked[:TARGET_COUNT]


def merge_rows(existing_rows: list[dict[str, str]], ranked_top: list[dict[str, Any]]) -> tuple[
    list[dict[str, str]], list[str], list[str]
]:
    merged = list(existing_rows)
    existing_tickers = {r["Ticker"].upper() for r in existing_rows if r.get("Ticker")}
    existing_names = {
        normalize_company_name(r["Company"]) for r in existing_rows if normalize_company_name(r["Company"])
    }

    skipped_ticker: list[str] = []
    skipped_name: list[str] = []

    for row in ranked_top:
        ticker = str(row["Symbol"]).upper()
        name = str(row["Company"]).strip()
        normalized = normalize_company_name(name)

        if ticker and ticker in existing_tickers:
            skipped_ticker.append(ticker)
            continue
        if normalized and normalized in existing_names:
            skipped_name.append(name)
            continue

        merged.append(
            {
                "Company": name,
                "Ticker": ticker,
                "SearchQuery": f"{clean_search_name(name)} software engineer",
                "Sector": str(row.get("Sector", "")),
            }
        )
        existing_tickers.add(ticker)
        if normalized:
            existing_names.add(normalized)

    return merged, skipped_ticker, skipped_name


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Company", "Ticker", "SearchQuery", "Sector"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show results without writing file")
    args = parser.parse_args()

    if not COMPANIES_CSV.exists():
        raise SystemExit(f"Missing companies CSV at {COMPANIES_CSV}")

    existing_rows = load_existing_rows(COMPANIES_CSV)
    constituents = fetch_constituents()
    market_caps = fetch_financial_caps()
    ranked_top = enrich_and_rank(constituents, market_caps)
    merged, skipped_ticker, skipped_name = merge_rows(existing_rows, ranked_top)

    if args.dry_run:
        print(f"Dry-run complete. Existing rows: {len(existing_rows)}")
        print(f"Top-ranked rows considered: {len(ranked_top)}")
        print(f"Ticker duplicates skipped: {len(skipped_ticker)}")
        print(f"Name duplicates skipped: {len(skipped_name)}")
        print(f"Merged row count: {len(merged)}")
        return 0

    write_rows(COMPANIES_CSV, merged)
    print(f"Wrote {len(merged)} rows to {COMPANIES_CSV}")
    print(f"Ticker duplicates skipped: {len(skipped_ticker)}")
    print(f"Name duplicates skipped: {len(skipped_name)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

