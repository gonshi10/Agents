#!/usr/bin/env python3
"""Basic smoke tests for earnings agent wiring."""

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
    print("\nTesting EarningsAgent import...")
    try:
        from agents.earnings_agent.agent import EarningsAgent  # noqa: F401
        print("✓ EarningsAgent imported successfully")
        return True
    except ImportError as exc:
        print(f"✗ EarningsAgent import failed: {exc}")
        return False


def main() -> int:
    print("=== Earnings Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("EarningsAgent Import", test_agent_import),
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

