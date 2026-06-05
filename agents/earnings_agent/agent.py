"""Core earnings agent implementation."""

from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta
from typing import Any

from common.clients.finnhub import FinnhubClient
from common.clients.openai_client import OpenAIClient
from common.config import Settings
from common.email.sender import EmailSender
from common.watchlist import load_tickers

from .prompts import BATCH_TEMPLATE_HEADER, SINGLE_TICKER_TEMPLATE, SYSTEM_PROMPT


class EarningsAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.finnhub = FinnhubClient(api_key=settings.finnhub_api_key)
        self.openai = OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            calls_per_minute=3,
        )
        self.email_sender = EmailSender(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_pass=settings.smtp_pass,
            default_to=settings.email_to,
        )

        self.insights_cache: dict[str, dict[str, str]] = {}
        self.sector_cache: dict[str, str] = {}

        print("✓ Configuration loaded successfully")
        print("📊 Finnhub rate limiting enabled via shared client")
        if self.openai.is_enabled:
            print("✅ OpenAI SDK client initialized")
        else:
            print("⚠️ OpenAI API key not set - AI insights will be disabled")

    def get_company_sector(self, ticker: str) -> str:
        if ticker in self.sector_cache:
            return self.sector_cache[ticker]

        profile = self.finnhub.get_stock_profile(ticker)
        sector = str(profile.get("finnhubIndustry", ""))
        industry = str(profile.get("finnhubIndustry", ""))
        expert_type = self.map_sector_to_expert(sector, industry, ticker)
        self.sector_cache[ticker] = expert_type
        return expert_type

    def map_sector_to_expert(self, sector: str, industry: str, ticker: str) -> str:
        sector_lower = sector.lower() if sector else ""
        industry_lower = industry.lower() if industry else ""

        if any(
            keyword in sector_lower or keyword in industry_lower
            for keyword in [
                "technology",
                "tech",
                "software",
                "hardware",
                "semiconductor",
                "internet",
                "cloud",
                "saas",
                "ai",
                "cybersecurity",
            ]
        ):
            return "Tech Analyst"
        if any(
            keyword in sector_lower or keyword in industry_lower
            for keyword in [
                "healthcare",
                "health",
                "pharmaceutical",
                "biotech",
                "medical",
                "pharma",
            ]
        ):
            return "Healthcare Specialist"
        if any(
            keyword in sector_lower or keyword in industry_lower
            for keyword in ["energy", "oil", "gas", "renewable", "solar", "wind", "utilities"]
        ):
            return "Energy Expert"
        if any(
            keyword in sector_lower or keyword in industry_lower
            for keyword in ["financial", "banking", "insurance", "investment", "lending"]
        ):
            return "Financial Services Analyst"

        tech_tickers = {"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "NFLX"}
        healthcare_tickers = {"JNJ", "PFE", "UNH", "ABBV", "MRK", "TMO", "ABT", "DHR"}
        financial_tickers = {"JPM", "BAC", "WFC", "GS", "MS", "C", "BLK"}
        if ticker in tech_tickers:
            return "Tech Analyst"
        if ticker in healthcare_tickers:
            return "Healthcare Specialist"
        if ticker in financial_tickers:
            return "Financial Services Analyst"
        return "General Financial Analyst"

    @staticmethod
    def _format_number(value: Any) -> str:
        if value in (None, "N/A"):
            return "N/A"
        try:
            return f"{float(value):.2f}"
        except (ValueError, TypeError):
            return str(value)

    def extract_guidance_insights(self, news_data: list[dict[str, Any]]) -> list[str]:
        guidance_insights: list[str] = []
        for item in news_data:
            headline = str(item.get("headline", "")).lower()
            if any(k in headline for k in ["guidance", "outlook", "forecast", "expects", "targets"]):
                guidance_insights.append(f"GUIDANCE: {item.get('headline', 'N/A')}")
            elif any(k in headline for k in ["strategic", "initiative", "expansion", "acquisition"]):
                guidance_insights.append(f"STRATEGIC: {item.get('headline', 'N/A')}")
            elif any(k in headline for k in ["restructuring", "cost cutting", "efficiency"]):
                guidance_insights.append(f"OPERATIONAL: {item.get('headline', 'N/A')}")
            elif any(k in headline for k in ["investor", "conference", "call", "press release"]):
                guidance_insights.append(f"INVESTOR RELATIONS: {item.get('headline', 'N/A')}")
        return guidance_insights[:3]

    def optimize_context_for_tokens(self, tickers_data: dict[str, dict[str, Any]]) -> str:
        parts = [BATCH_TEMPLATE_HEADER, ""]
        for ticker, data in tickers_data.items():
            earnings = data["earnings"]
            news = data["news"]
            expert_type = self.get_company_sector(ticker)
            guidance = self.extract_guidance_insights(news)
            parts.append(
                (
                    f"{ticker} (Sector Expert: {expert_type}):\n"
                    f"EPS: {self._format_number(earnings.get('epsEstimate'))}"
                    f"→{self._format_number(earnings.get('epsActual'))}\n"
                    f"Revenue: {self._format_number(earnings.get('revenueEstimate'))}"
                    f"→{self._format_number(earnings.get('revenueActual'))}\n"
                    f"Guidance & Strategic Context: "
                    f"{' | '.join(guidance) if guidance else 'Limited guidance available'}\n"
                )
            )
        return "\n".join(parts)

    def parse_structured_insights(self, response_text: str, ticker: str) -> dict[str, str]:
        result = {
            "summary": "",
            "strategic_analysis": "",
            "risk_factors": "",
            "investment_recommendation": "HOLD (Medium Confidence)",
            "expert_recommendation": self.get_company_sector(ticker),
        }
        if not response_text:
            return result

        lines = response_text.split("\n")
        current_section: str | None = None
        current_content: list[str] = []

        for raw in lines:
            line = raw.strip()
            if not line:
                if current_section and current_content:
                    result[current_section] = " ".join(current_content)
                    current_content = []
                continue

            if "EXECUTIVE SUMMARY" in line.upper():
                if current_section and current_content:
                    result[current_section] = " ".join(current_content)
                current_section, current_content = "summary", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "STRATEGIC ANALYSIS" in line.upper():
                if current_section and current_content:
                    result[current_section] = " ".join(current_content)
                current_section, current_content = "strategic_analysis", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "RISK FACTORS" in line.upper() or "RISK FACTOR" in line.upper():
                if current_section and current_content:
                    result[current_section] = " ".join(current_content)
                current_section, current_content = "risk_factors", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "INVESTMENT RECOMMENDATION" in line.upper():
                if ":" in line:
                    value = line.split(":", 1)[1].strip()
                    if value:
                        result["investment_recommendation"] = value
                current_section = None
            elif "EXPERT RECOMMENDATION" in line.upper():
                if ":" in line:
                    value = line.split(":", 1)[1].strip()
                    if value:
                        result["expert_recommendation"] = value
                current_section = None
            elif current_section:
                current_content.append(line)

        if current_section and current_content:
            result[current_section] = " ".join(current_content)
        if not result["summary"] and not result["strategic_analysis"]:
            result["summary"] = response_text[:500]
        return result

    def generate_ai_insights_single(
        self,
        ticker: str,
        earnings_data: dict[str, Any],
        news_data: list[dict[str, Any]],
    ) -> dict[str, str]:
        if not self.openai.is_enabled:
            return {
                "summary": "AI insights disabled - set OPENAI_API_KEY to enable",
                "strategic_analysis": "",
                "risk_factors": "",
                "investment_recommendation": "N/A",
                "expert_recommendation": "General Financial Analyst",
            }

        cache_key = f"{ticker}_{earnings_data.get('epsActual', 'N/A')}"
        if cache_key in self.insights_cache:
            return self.insights_cache[cache_key]

        expert_type = self.get_company_sector(ticker)
        context = SINGLE_TICKER_TEMPLATE.format(
            ticker=ticker,
            expert_type=expert_type,
            eps_est=self._format_number(earnings_data.get("epsEstimate")),
            eps_act=self._format_number(earnings_data.get("epsActual")),
            rev_est=self._format_number(earnings_data.get("revenueEstimate")),
            rev_act=self._format_number(earnings_data.get("revenueActual")),
            news=", ".join([str(item.get("headline", "N/A"))[:50] for item in news_data[:2]]),
        )

        try:
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=600,
            )
            parsed = self.parse_structured_insights(content, ticker)
            self.insights_cache[cache_key] = parsed
            return parsed
        except Exception as exc:
            return {
                "summary": f"AI insights unavailable: {exc}",
                "strategic_analysis": "",
                "risk_factors": "",
                "investment_recommendation": "N/A",
                "expert_recommendation": expert_type,
            }

    def generate_individual_insights(self, tickers_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
        insights: dict[str, dict[str, str]] = {}
        for i, (ticker, data) in enumerate(tickers_data.items()):
            insights[ticker] = self.generate_ai_insights_single(ticker, data["earnings"], data["news"])
            if i < len(tickers_data) - 1:
                time.sleep(random.uniform(10, 15))
        return insights

    def generate_batched_ai_insights(self, tickers_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
        if not self.openai.is_enabled:
            default = {
                "summary": "AI insights disabled - set OPENAI_API_KEY to enable",
                "strategic_analysis": "",
                "risk_factors": "",
                "investment_recommendation": "N/A",
                "expert_recommendation": "General Financial Analyst",
            }
            return {ticker: default.copy() for ticker in tickers_data}

        def primary() -> dict[str, dict[str, str]]:
            context = self.optimize_context_for_tokens(tickers_data)
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=600 * max(len(tickers_data), 1),
            )
            parsed: dict[str, dict[str, str]] = {}
            for ticker in tickers_data:
                parsed[ticker] = self.parse_structured_insights(content, ticker)
            return parsed

        return self.openai.run_with_fallback(primary, lambda: self.generate_individual_insights(tickers_data))

    def _is_meaningful_summary(self, summary_text: str) -> bool:
        if not summary_text or len(summary_text.strip()) < 50:
            return False
        summary_lower = summary_text.lower()
        strategic_keywords = [
            "implication",
            "strategic",
            "competitive",
            "market",
            "outlook",
            "guidance",
            "position",
            "growth",
            "trajectory",
            "opportunity",
        ]
        stat_phrases = [
            "eps of",
            "revenue of",
            "beat expectations",
            "missed expectations",
            "actual eps",
            "actual revenue",
        ]
        has_strategic = any(keyword in summary_lower for keyword in strategic_keywords)
        stat_count = sum(1 for phrase in stat_phrases if phrase in summary_lower)
        if len(summary_text) < 100 and stat_count >= 1 and not has_strategic:
            return False
        return has_strategic or stat_count == 0

    def _format_revenue(self, value: Any) -> str:
        if value in (None, "N/A"):
            return "N/A"
        try:
            val = float(value)
            if val >= 1_000_000_000:
                return f"{val / 1_000_000_000:.2f}B"
            return f"{val / 1_000_000:.2f}M"
        except (ValueError, TypeError):
            return str(value)

    def create_email_content(
        self,
        ticker: str,
        earnings_data: dict[str, Any],
        news_data: list[dict[str, Any]],
        ai_insights: dict[str, str],
    ) -> tuple[str, str]:
        eps_est = self._format_number(earnings_data.get("epsEstimate"))
        eps_act = self._format_number(earnings_data.get("epsActual"))
        rev_est = self._format_revenue(earnings_data.get("revenueEstimate"))
        rev_act = self._format_revenue(earnings_data.get("revenueActual"))

        summary = ai_insights.get("summary", "No summary available")
        strategic = ai_insights.get("strategic_analysis", "")
        risks = ai_insights.get("risk_factors", "")
        recommendation = ai_insights.get("investment_recommendation", "HOLD (Medium Confidence)")
        expert = ai_insights.get("expert_recommendation", "General Financial Analyst")

        insights_html_sections: list[str] = []
        if summary and self._is_meaningful_summary(summary):
            insights_html_sections.append(f"<h4>Executive Summary</h4><p>{summary}</p>")
        if strategic:
            insights_html_sections.append(f"<h4>Strategic Analysis</h4><p>{strategic}</p>")
        if risks:
            insights_html_sections.append(f"<h4>Risk Factors</h4><p>{risks}</p>")
        if not insights_html_sections:
            insights_html_sections.append("<p>No insights available.</p>")

        news_html = "".join(
            [
                f"<li><a href=\"{item.get('url', '#')}\">{item.get('headline', 'N/A')}</a></li>"
                for item in news_data[:3]
            ]
        )

        html_content = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #222;">
  <h2>{ticker} Earnings Report</h2>
  <h3>Financial Results</h3>
  <p><strong>EPS:</strong> {eps_est} -> {eps_act}</p>
  <p><strong>Revenue:</strong> {rev_est} -> {rev_act}</p>
  <h3>Investment Recommendation</h3>
  <p>{recommendation}</p>
  <h3>Expert Recommendation</h3>
  <p>{expert}</p>
  <h3>AI Insights</h3>
  {''.join(insights_html_sections)}
  <h3>Recent News</h3>
  <ul>{news_html}</ul>
  <hr />
  <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</body>
</html>
"""

        plain_news = "\n".join([f"- {item.get('headline', 'N/A')}" for item in news_data[:3]])
        plain_content = f"""
{ticker} EARNINGS REPORT
======================

FINANCIAL RESULTS
-----------------
EPS: {eps_est} -> {eps_act}
Revenue: {rev_est} -> {rev_act}

INVESTMENT RECOMMENDATION
-------------------------
{recommendation}

EXPERT RECOMMENDATION
---------------------
{expert}

AI INSIGHTS
-----------
EXECUTIVE SUMMARY:
{summary}

STRATEGIC ANALYSIS:
{strategic or 'No strategic analysis available'}

RISK FACTORS:
{risks or 'No risk factors identified'}

RECENT NEWS
-----------
{plain_news}

Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        plain_content = re.sub(r"<[^>]+>", "", plain_content)
        return html_content, plain_content

    def run(self, test_mode: bool = False) -> None:
        print("🚀 Starting Earnings Agent")
        target_date = (
            (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
            if test_mode
            else (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        )
        print(f"📅 Checking earnings for: {target_date}")

        tickers = load_tickers(self.settings.watchlist_csv)
        if not tickers:
            print("❌ No tickers loaded. Exiting.")
            return

        tickers_data: dict[str, dict[str, Any]] = {}
        for i, ticker in enumerate(tickers, 1):
            print(f"--- Processing {ticker} ({i}/{len(tickers)}) ---")
            earnings = self.finnhub.get_earnings_calendar(ticker, target_date)
            if not earnings:
                continue
            news = self.finnhub.get_company_news(ticker, target_date)
            tickers_data[ticker] = {"earnings": earnings, "news": news}

        if not tickers_data:
            print("❌ No earnings data found. Exiting.")
            return

        ai_insights = self.generate_batched_ai_insights(tickers_data)
        emails_sent = 0
        for ticker, data in tickers_data.items():
            subject = f"{ticker} Earnings Report"
            ticker_insights = ai_insights.get(ticker, {})
            html_content, plain_content = self.create_email_content(
                ticker=ticker,
                earnings_data=data["earnings"],
                news_data=data["news"],
                ai_insights=ticker_insights,
            )
            if self.email_sender.send(subject, html_content, plain_content):
                emails_sent += 1

        print(f"🎉 Processing complete! Sent {emails_sent} emails for {target_date}")

