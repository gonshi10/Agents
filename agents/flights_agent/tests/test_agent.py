#!/usr/bin/env python3
"""Basic smoke tests for flights agent wiring (offline, no network)."""

import os
import sys


def test_imports() -> bool:
    print("Testing imports...")
    try:
        import requests  # noqa: F401
        from dotenv import load_dotenv  # noqa: F401
        print("✓ Core imports available")
        return True
    except ImportError as exc:
        print(f"✗ Import failed: {exc}")
        return False


def test_config() -> bool:
    print("\nTesting configuration...")
    required_vars = ["FINNHUB_API_KEY", "SMTP_USER", "SMTP_PASS", "EMAIL_TO"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}")
        return False
    if not os.getenv("FLIGHTS_API_TOKEN"):
        print("ℹ️ FLIGHTS_API_TOKEN not set - live runs will be a no-op (offline tests still pass)")
    print("✓ All required environment variables found")
    return True


def test_agent_import() -> bool:
    print("\nTesting FlightsAgent import...")
    try:
        from agents.flights_agent.agent import FlightsAgent  # noqa: F401
        print("✓ FlightsAgent imported successfully")
        return True
    except ImportError as exc:
        print(f"✗ FlightsAgent import failed: {exc}")
        return False


def test_route_loading() -> bool:
    print("\nTesting route CSV loading...")
    try:
        from common.watchlist import load_routes

        path = os.path.join(os.path.dirname(__file__), "..", "data", "routes.csv")
        routes = load_routes(path)
        assert len(routes) == 2, f"expected 2 sample routes, got {len(routes)}"
        first = routes[0]
        assert first["origin"] == "TLV" and first["destination"] == "JFK"
        assert first["depart_month"] == "2026-09"
        assert first["max_price"] == 650.0
        assert first["one_way"] is False
        assert routes[1]["one_way"] is True and routes[1]["return_month"] is None
        print("✓ Route loading behaves as expected")
        return True
    except Exception as exc:
        print(f"✗ Route loading test failed: {exc}")
        return False


def test_detection_logic() -> bool:
    """Exercise the pure change-detection helpers without any network calls."""
    print("\nTesting change-detection logic...")
    try:
        from agents.flights_agent.agent import FlightsAgent

        # Bypass __init__ (which builds network clients) — we only need methods.
        agent = FlightsAgent.__new__(FlightsAgent)
        agent.drop_pct = 10.0

        route = {
            "origin": "TLV",
            "destination": "JFK",
            "depart_month": "2026-09",
            "return_month": "2026-09",
            "max_price": 650.0,
            "one_way": False,
        }

        # First-seen, at/below target -> alert even with no prior price.
        change = agent.detect_change(route, {"price": 600.0}, None)
        assert change is not None and any("target" in r.lower() for r in change["reasons"])

        # First-seen, above target -> no alert (nothing to compare for a drop).
        assert agent.detect_change(route, {"price": 900.0}, None) is None

        # Drop >= threshold vs snapshot -> alert (route above target so only drop fires).
        no_target = {**route, "max_price": None}
        dropped = agent.detect_change(no_target, {"price": 800.0}, {"price": 1000.0})
        assert dropped is not None and dropped["pct"] == 20.0, f"expected 20% drop, got {dropped}"

        # Small drop under threshold, no target -> no alert.
        assert agent.detect_change(no_target, {"price": 970.0}, {"price": 1000.0}) is None

        # Price rise, no target -> no alert.
        assert agent.detect_change(no_target, {"price": 1100.0}, {"price": 1000.0}) is None

        # route_key includes return + one-way markers distinctly.
        ow = {**route, "one_way": True, "return_month": None}
        assert agent.route_key(route) != agent.route_key(ow)

        print("✓ Detection logic behaves as expected")
        return True
    except Exception as exc:
        print(f"✗ Detection logic test failed: {exc}")
        return False


def main() -> int:
    print("=== Flights Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("FlightsAgent Import", test_agent_import),
        ("Route Loading", test_route_loading),
        ("Detection Logic", test_detection_logic),
    ]
    results: list[tuple[str, bool]] = []
    for name, fn in tests:
        try:
            results.append((name, fn()))
        except Exception as exc:
            print(f"✗ {name} test failed with exception: {exc}")
            results.append((name, False))

    print("\n=== Test Results ===")
    for name, ok in results:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
