#!/usr/bin/env python3
"""Debug script to test earnings agent AI insights."""

from common.config import get_settings
from agents.earnings_agent.agent import EarningsAgent


def test_ai_insights_generation() -> None:
    print("🧪 DEBUGGING AI INSIGHTS GENERATION")
    print("=" * 50)
    agent = EarningsAgent(get_settings())

    mock_tickers_data = {
        "AAPL": {
            "earnings": {
                "period": "Q1 2024",
                "epsEstimate": "1.50",
                "epsActual": "1.75",
                "revenueEstimate": "1000000000",
                "revenueActual": "1100000000",
            },
            "news": [
                {"headline": "Apple beats earnings expectations"},
                {"headline": "Strong iPhone sales reported"},
            ],
        }
    }

    single = agent.generate_ai_insights_single(
        "AAPL",
        mock_tickers_data["AAPL"]["earnings"],
        mock_tickers_data["AAPL"]["news"],
    )
    print("Single insight:", single)
    batched = agent.generate_batched_ai_insights(mock_tickers_data)
    print("Batch insights:", batched)


if __name__ == "__main__":
    test_ai_insights_generation()

