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
        assert len(companies) >= 200, f"expected >=200 companies, got {len(companies)}"
        tickers = [c["ticker"] for c in companies if c.get("ticker")]
        names = {c["company"].strip().lower() for c in companies}
        assert "AAPL" in tickers and "MSFT" in tickers and "NVDA" in tickers
        assert "stripe" in names and "anthropic" in names
        assert len(tickers) == len(set(tickers)), "duplicate tickers detected"
        assert all(c.get("search_query", "").strip() for c in companies), "empty search_query detected"
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
        assert counts.get("Python", 0) == 0, "programming languages should not be tracked"
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


def test_batch_parser_splits_technologies() -> bool:
    print("\nTesting batch parser splits technologies...")
    try:
        from agents.techstack_agent.agent import TechstackAgent

        agent = TechstackAgent.__new__(TechstackAgent)
        mock_response = """
TECHNOLOGY: Kubernetes
SECTOR READ: CNCF-backed orchestration platform; multi-employer hiring signals durable platform spend.
INVESTMENT VIEW: WATCH - Cloud-native shift supports infra vendors more than a single ticker.
CONFIDENCE: MEDIUM - Multiple employers but limited posting sample.
EXPERT RECOMMENDATION: Cloud & DevOps Specialist

TECHNOLOGY: Kafka
SECTOR READ: Confluent monetizes stream processing; rising mentions imply pipeline modernization budgets.
INVESTMENT VIEW: BUY - Enterprise data motion budgets are expanding into real-time stacks.
CONFIDENCE: HIGH - Market-wide adoption across sectors.
EXPERT RECOMMENDATION: Data Infrastructure Analyst
"""
        parsed = agent.parse_structured_insights(mock_response, ["Kubernetes", "Kafka"])
        k8s = parsed["Kubernetes"]
        kafka = parsed["Kafka"]

        if k8s["sector_read"] == kafka["sector_read"]:
            print("✗ Batch parser returned identical sector reads for different technologies")
            return False
        if "orchestration" not in k8s["sector_read"].lower():
            print(f"✗ Kubernetes sector_read missing expected content: {k8s['sector_read']!r}")
            return False
        if "BUY" not in kafka["investment_view"].upper():
            print(f"✗ Kafka investment_view missing BUY: {kafka['investment_view']!r}")
            return False
        if "Data Infrastructure Analyst" not in kafka["expert_recommendation"]:
            print(
                f"✗ Kafka expert_recommendation missing expected expert: "
                f"{kafka['expert_recommendation']!r}"
            )
            return False
        print("✓ Batch parser returns distinct insights per technology")
        return True
    except Exception as exc:
        print(f"✗ Batch parser test failed: {exc}")
        return False


def test_email_badges_not_escaped() -> bool:
    print("\nTesting email badge HTML rendering...")
    try:
        from agents.techstack_agent.agent import TechstackAgent

        agent = TechstackAgent.__new__(TechstackAgent)
        signals = {
            "Kubernetes": {
                "category": "CloudInfraDevOps",
                "rising": ["Apple"],
                "new": ["Stripe"],
                "falling": [],
                "avg_delta": 12.5,
                "market_wide": True,
            }
        }
        insights = {
            "Kubernetes": {
                "sector_read": (
                    "CNCF-backed orchestration platform signals durable cloud-native platform spend "
                    "across large employers."
                ),
                "investment_view": "WATCH - Infra modernization supports platform vendors broadly.",
                "confidence": "MEDIUM - Strong cross-employer signal.",
                "expert_recommendation": "Cloud & DevOps Specialist",
            }
        }
        _, html_content, _ = agent.create_digest_email(signals, insights, market_overview="")
        if "&lt;span" in html_content:
            print("✗ Email HTML contains escaped badge markup")
            return False
        if "Apple" not in html_content:
            print("✗ Email HTML missing rendered company badge text")
            return False
        if '<span style="display:inline-block;' not in html_content:
            print("✗ Email HTML missing rendered badge span")
            return False
        print("✓ Email badges render as HTML, not escaped text")
        return True
    except Exception as exc:
        print(f"✗ Email badge HTML test failed: {exc}")
        return False


def test_email_layout_structure() -> bool:
    print("\nTesting email layout structure...")
    try:
        from common.email import templates as et
        from agents.techstack_agent.agent import TechstackAgent

        et.section_heading("x")
        et.momentum_row("Data Platforms", 1, 0, 0, 1)

        agent = TechstackAgent.__new__(TechstackAgent)
        signals = {
            "Kubernetes": {
                "category": "CloudInfraDevOps",
                "rising": ["Apple"],
                "new": [],
                "falling": [],
                "avg_delta": 12.5,
                "market_wide": True,
            },
            "Kafka": {
                "category": "DataPlatforms",
                "rising": ["Microsoft"],
                "new": [],
                "falling": [],
                "avg_delta": 8.0,
                "market_wide": False,
            },
        }
        insights = {
            "Kubernetes": {
                "sector_read": (
                    "CNCF-backed orchestration platform signals durable cloud-native platform spend "
                    "across large employers."
                ),
                "investment_view": "WATCH - Infra modernization supports platform vendors broadly.",
                "confidence": "MEDIUM - Strong cross-employer signal.",
                "expert_recommendation": "Cloud & DevOps Specialist",
            },
            "Kafka": {
                "sector_read": (
                    "Confluent monetizes stream processing and rising mentions imply pipeline "
                    "modernization budgets across enterprise data teams."
                ),
                "investment_view": "BUY - Real-time data motion budgets are expanding.",
                "confidence": "HIGH - Cross-sector adoption signal.",
                "expert_recommendation": "Data Infrastructure Analyst",
            },
        }
        overview = "Cloud and data platform hiring accelerated across tracked employers this month."
        _, html_content, plain_content = agent.create_digest_email(
            signals, insights, market_overview=overview
        )
        cloud_devops_html = et.esc("Cloud & DevOps")
        required_fragments = [
            "This Month at a Glance",
            overview,
            "Top Signals",
            cloud_devops_html,
            "Category Momentum",
        ]
        for fragment in required_fragments:
            if fragment not in html_content:
                print(f"✗ Email HTML missing expected fragment: {fragment!r}")
                return False
        if "&lt;span" in html_content:
            print("✗ Email HTML contains escaped badge markup")
            return False
        if "THIS MONTH AT A GLANCE" not in plain_content:
            print("✗ Plain text missing overview section header")
            return False
        if "Cloud & DevOps" not in plain_content:
            print("✗ Plain text missing human-readable category label")
            return False
        print("✓ Email layout includes overview, headings, and readable category labels")
        return True
    except Exception as exc:
        print(f"✗ Email layout structure test failed: {exc}")
        return False


def main() -> int:
    print("=== Techstack Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("TechstackAgent Import", test_agent_import),
        ("Company Loading", test_company_loading),
        ("Detection Logic", test_detection_logic),
        ("Batch Parser", test_batch_parser_splits_technologies),
        ("Email Badge HTML", test_email_badges_not_escaped),
        ("Email Layout Structure", test_email_layout_structure),
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

