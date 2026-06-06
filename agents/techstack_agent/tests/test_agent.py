#!/usr/bin/env python3
"""Basic smoke tests for techstack agent wiring (offline, no network)."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


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
    if not os.getenv("ADZUNA_APP_ID") or not os.getenv("ADZUNA_APP_KEY"):
        print("ℹ️ ADZUNA_APP_ID/ADZUNA_APP_KEY not set - live runs will be a no-op")
    print("✓ All required environment variables found")
    return True


def test_agent_import() -> bool:
    print("\nTesting TechstackAgent import...")
    try:
        from agents.techstack_agent.agent import TechstackAgent  # noqa: F401
        print("✓ TechstackAgent imported successfully")
        return True
    except ImportError as exc:
        print(f"✗ TechstackAgent import failed: {exc}")
        return False


def test_company_loading() -> bool:
    print("\nTesting companies CSV loading...")
    try:
        from common.watchlist import load_companies

        path = os.path.join(os.path.dirname(__file__), "..", "data", "companies.csv")
        companies = load_companies(path)
        assert len(companies) >= 4, f"expected >=4 sample companies, got {len(companies)}"
        first = companies[0]
        assert first["company"] == "Apple"
        assert first["ticker"] == "AAPL"
        assert first["search_query"]
        print("✓ Company loading behaves as expected")
        return True
    except Exception as exc:
        print(f"✗ Company loading test failed: {exc}")
        return False


def test_detection_logic() -> bool:
    print("\nTesting extraction + trend logic...")
    try:
        from agents.techstack_agent.agent import TechstackAgent

        agent = TechstackAgent.__new__(TechstackAgent)
        agent.trend_threshold = 10.0
        agent._compiled_patterns = None

        postings = [
            {"title": "Backend Engineer", "description": "Python, Kafka, Kubernetes"},
            {"title": "ML Engineer", "description": "PyTorch and Kubernetes"},
            {"title": "Platform Engineer", "description": "Terraform and AWS"},
        ]
        counts, total = agent.extract_tech_mentions(postings)
        assert total == 3
        assert counts.get("Kubernetes", 0) >= 2

        previous = {"technologies": {"Kubernetes": 0, "Kafka": 1}, "total": 10}
        current = {"Kubernetes": 5, "Kafka": 0}
        trends = agent.detect_company_trends(
            company={"company": "Acme", "ticker": "ACME"},
            current_counts=current,
            current_total=10,
            previous_entry=previous,
        )
        assert any(
            t["technology"] == "Kubernetes" and t["direction"] in {"NEW", "RISING"}
            for t in trends
        )
        assert any(t["technology"] == "Kafka" and t["direction"] == "FALLING" for t in trends)
        assert all(t.get("category") for t in trends)

        grouped = agent.detect_cross_company_trends(trends)
        assert "Kubernetes" in grouped
        category_summary = agent.summarize_category_momentum(grouped)
        assert category_summary, "category momentum summary should not be empty"
        print("✓ Detection logic behaves as expected")
        return True
    except Exception as exc:
        print(f"✗ Detection logic test failed: {exc}")
        return False


def main() -> int:
    print("=== Techstack Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("TechstackAgent Import", test_agent_import),
        ("Company Loading", test_company_loading),
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

