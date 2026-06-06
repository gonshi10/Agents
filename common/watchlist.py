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


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_routes(csv_file: str) -> list[dict]:
    """Load flight routes from a CSV for the flights agent.

    Expected columns: Origin, Destination, DepartMonth (YYYY-MM) — required;
    ReturnMonth, MaxPrice, OneWay — optional. Rows missing a required field are
    skipped. Origin/Destination are upper-cased; MaxPrice is parsed to float (or
    None); OneWay is parsed to bool.
    """
    routes: list[dict] = []
    try:
        with open(csv_file, "r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                origin = str(row.get("Origin", "")).strip().upper()
                destination = str(row.get("Destination", "")).strip().upper()
                depart_month = str(row.get("DepartMonth", "")).strip()
                if not (origin and destination and depart_month):
                    continue
                return_month = str(row.get("ReturnMonth", "")).strip() or None
                one_way = str(row.get("OneWay", "")).strip().lower() in {"1", "true", "yes", "on"}
                routes.append(
                    {
                        "origin": origin,
                        "destination": destination,
                        "depart_month": depart_month,
                        "return_month": return_month,
                        "max_price": _as_float(row.get("MaxPrice")),
                        "one_way": one_way,
                    }
                )
    except Exception as exc:
        print(f"✗ Failed to load routes from {csv_file}: {exc}")
        return []

    print(
        f"✓ Loaded {len(routes)} routes: "
        + ", ".join(f"{r['origin']}→{r['destination']}" for r in routes[:5])
        + ("..." if len(routes) > 5 else "")
    )
    return routes


def load_companies(csv_file: str) -> list[dict]:
    """Load tracked companies for the techstack agent.

    Expected columns: Company, SearchQuery (required).
    Optional columns: Ticker, Sector.
    """
    companies: list[dict] = []
    try:
        with open(csv_file, "r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                company = str(row.get("Company", "")).strip()
                search_query = str(row.get("SearchQuery", "")).strip()
                if not (company and search_query):
                    continue
                ticker = str(row.get("Ticker", "")).strip().upper()
                sector = str(row.get("Sector", "")).strip()
                companies.append(
                    {
                        "company": company,
                        "ticker": ticker or None,
                        "search_query": search_query,
                        "sector": sector or None,
                    }
                )
    except Exception as exc:
        print(f"✗ Failed to load companies from {csv_file}: {exc}")
        return []

    print(
        f"✓ Loaded {len(companies)} companies: "
        + ", ".join(c["company"] for c in companies[:5])
        + ("..." if len(companies) > 5 else "")
    )
    return companies

