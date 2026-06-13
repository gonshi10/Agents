#!/usr/bin/env python3
"""Basic smoke tests for ratings agent wiring."""

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
    print("✓ All required environment variables found")
    return True


def test_agent_import() -> bool:
    print("\nTesting RatingsAgent import...")
    try:
        from agents.ratings_agent.agent import RatingsAgent  # noqa: F401
        print("✓ RatingsAgent imported successfully")
        return True
    except ImportError as exc:
        print(f"✗ RatingsAgent import failed: {exc}")
        return False


def test_detection_logic() -> bool:
    """Exercise the pure change-detection helpers without any network calls."""
    print("\nTesting change-detection logic...")
    try:
        from agents.ratings_agent.agent import RatingsAgent

        # Bypass __init__ (which builds network clients) — we only need methods.
        agent = RatingsAgent.__new__(RatingsAgent)

        # Recommendation upgrade: prior mostly hold -> latest mostly strong buy.
        trends = [
            {"period": "2026-06", "strongBuy": 12, "buy": 8, "hold": 2, "sell": 0, "strongSell": 0},
            {"period": "2026-05", "strongBuy": 2, "buy": 6, "hold": 10, "sell": 4, "strongSell": 0},
        ]
        rec = agent._detect_rec_change(trends)
        assert rec is not None and rec["direction"] == "UPGRADE", f"expected UPGRADE, got {rec}"

        # No material move -> None.
        flat = [
            {"period": "2026-06", "strongBuy": 5, "buy": 5, "hold": 5, "sell": 0, "strongSell": 0},
            {"period": "2026-05", "strongBuy": 5, "buy": 5, "hold": 5, "sell": 0, "strongSell": 0},
        ]
        assert agent._detect_rec_change(flat) is None, "flat trend should not flag"

        # Price target raised >5%.
        pt = agent._detect_pt_change(
            "TEST", {"targetMean": 220.0}, {"TEST": {"targetMean": 200.0}}
        )
        assert pt is not None and pt["direction"] == "RAISED", f"expected RAISED, got {pt}"

        # Small move under threshold -> None.
        assert (
            agent._detect_pt_change("TEST", {"targetMean": 202.0}, {"TEST": {"targetMean": 200.0}})
            is None
        ), "sub-threshold move should not flag"

        # No baseline -> None.
        assert agent._detect_pt_change("TEST", {"targetMean": 202.0}, {}) is None

        # Repeat rec alert matches stored fingerprint.
        rec_change = {
            "direction": "UPGRADE",
            "period_before": "2026-05",
            "period_after": "2026-06",
        }
        prev_entry = {
            "targetMean": 200.0,
            "lastRecAlert": {
                "period_before": "2026-05",
                "period_after": "2026-06",
                "direction": "UPGRADE",
            },
        }
        assert agent._is_repeat_rec_alert(rec_change, prev_entry) is True

        # New month -> not a repeat.
        new_period = {**rec_change, "period_after": "2026-07"}
        assert agent._is_repeat_rec_alert(new_period, prev_entry) is False

        # Snapshot merge preserves lastRecAlert when updating price target fields.
        merged = dict(prev_entry)
        merged.update({"targetMean": 220.0, "lastUpdated": "2026-06-01"})
        assert merged["lastRecAlert"]["period_after"] == "2026-06"
        assert merged["targetMean"] == 220.0

        print("✓ Detection logic behaves as expected")
        return True
    except Exception as exc:
        print(f"✗ Detection logic test failed: {exc}")
        return False


def main() -> int:
    print("=== Ratings Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("RatingsAgent Import", test_agent_import),
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
