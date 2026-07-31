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


def test_batch_parser_splits_tickers() -> bool:
    print("\nTesting batch parser splits tickers...")
    from agents.earnings_agent.agent import EarningsAgent

    agent = EarningsAgent.__new__(EarningsAgent)
    agent.get_company_sector = lambda ticker: "Tech Analyst"

    mock_response = """
AAPL:
EXECUTIVE SUMMARY: Apple showed strong iPhone momentum.
STRATEGIC ANALYSIS: Services growth accelerates.
GUIDANCE OUTLOOK: Management raised full-year outlook on AI demand.
RISK FACTORS: China exposure remains elevated.
ANALYST CONCLUSION: A solid beat with improving services mix supports a constructive view.
INVESTMENT RECOMMENDATION: BUY (High Confidence)
EXPERT RECOMMENDATION: Tech Analyst

MSFT:
EXECUTIVE SUMMARY: Microsoft cloud revenue drives upside.
STRATEGIC ANALYSIS: Azure gains share versus peers.
GUIDANCE OUTLOOK: Capex guidance signals continued AI infrastructure investment.
RISK FACTORS: Regulatory scrutiny on acquisitions.
ANALYST CONCLUSION: Cloud leadership intact despite rising spend.
INVESTMENT RECOMMENDATION: HOLD (Medium Confidence)
EXPERT RECOMMENDATION: Tech Analyst
"""
    parsed = agent.parse_structured_insights(mock_response, ["AAPL", "MSFT"])
    aapl = parsed["AAPL"]
    msft = parsed["MSFT"]

    if aapl["summary"] == msft["summary"]:
        print("✗ Batch parser returned identical summaries for different tickers")
        return False
    if "iPhone" not in aapl["summary"]:
        print(f"✗ AAPL summary missing expected content: {aapl['summary']!r}")
        return False
    if "cloud" not in msft["summary"].lower():
        print(f"✗ MSFT summary missing expected content: {msft['summary']!r}")
        return False
    if "outlook" not in aapl["guidance_outlook"].lower():
        print(f"✗ AAPL guidance_outlook missing expected content: {aapl['guidance_outlook']!r}")
        return False
    if "leadership" not in msft["analyst_conclusion"].lower():
        print(f"✗ MSFT analyst_conclusion missing expected content: {msft['analyst_conclusion']!r}")
        return False
    print("✓ Batch parser returns distinct insights per ticker")
    return True


def main() -> int:
    print("=== Earnings Agent Test Suite ===\n")
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("EarningsAgent Import", test_agent_import),
        ("Batch Parser", test_batch_parser_splits_tickers),
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

