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
from common.email import templates as et
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
        self.industry_cache: dict[str, str] = {}

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
        self.industry_cache[ticker] = industry or "N/A"
        return expert_type

    def get_company_industry(self, ticker: str) -> str:
        if ticker in self.industry_cache:
            return self.industry_cache[ticker]
        self.get_company_sector(ticker)
        return self.industry_cache.get(ticker, "N/A")

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

    @staticmethod
    def _surprise_pct(actual_raw: Any, estimate_raw: Any) -> str:
        if actual_raw in (None, "N/A") or estimate_raw in (None, "N/A"):
            return "N/A"
        try:
            actual = float(actual_raw)
            estimate = float(estimate_raw)
            if estimate == 0:
                return "N/A"
            pct = ((actual - estimate) / abs(estimate)) * 100
            return f"{pct:+.1f}%"
        except (ValueError, TypeError):
            return "N/A"

    @staticmethod
    def _format_market_context(
        trends: list[dict[str, Any]], price_target: dict[str, Any]
    ) -> dict[str, str]:
        breakdown = "N/A"
        if trends:
            latest = trends[0]
            parts = []
            for key in ("strongBuy", "buy", "hold", "sell", "strongSell"):
                val = latest.get(key)
                if val is not None:
                    parts.append(f"{key}={val}")
            if parts:
                breakdown = ", ".join(parts)

        pt_str = "N/A"
        pt_mean = price_target.get("targetMean")
        if pt_mean not in (None, 0, "0"):
            try:
                mean_val = float(pt_mean)
                pt_str = f"Mean ${mean_val:.2f}"
                pt_high = price_target.get("targetHigh")
                pt_low = price_target.get("targetLow")
                if pt_high not in (None, 0, "0") and pt_low not in (None, 0, "0"):
                    pt_str += f" (range ${float(pt_low):.2f}-${float(pt_high):.2f})"
            except (ValueError, TypeError):
                pt_str = "N/A"

        summary = f"Analyst breakdown (latest): {breakdown}; Price target: {pt_str}"
        return {"breakdown": breakdown, "price_target": pt_str, "summary": summary}

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

    def _build_ticker_context(
        self,
        ticker: str,
        earnings: dict[str, Any],
        news: list[dict[str, Any]],
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        mc = market_context or {}
        formatted_mc = self._format_market_context(
            mc.get("trends", []), mc.get("price_target", {})
        )
        guidance = self.extract_guidance_insights(news)
        headlines = "\n".join(
            f"- {item.get('headline', 'N/A')}" for item in news[:5]
        ) or "No relevant headlines"

        return {
            "ticker": ticker,
            "expert_type": self.get_company_sector(ticker),
            "industry": self.get_company_industry(ticker),
            "eps_est": self._format_number(earnings.get("epsEstimate")),
            "eps_act": self._format_number(earnings.get("epsActual")),
            "eps_surprise": self._surprise_pct(
                earnings.get("epsActual"), earnings.get("epsEstimate")
            ),
            "rev_est": self._format_revenue(earnings.get("revenueEstimate")),
            "rev_act": self._format_revenue(earnings.get("revenueActual")),
            "rev_surprise": self._surprise_pct(
                earnings.get("revenueActual"), earnings.get("revenueEstimate")
            ),
            "market_context": formatted_mc["summary"],
            "news": headlines,
            "guidance": " | ".join(guidance) if guidance else "Limited guidance available",
            "market_breakdown": formatted_mc["breakdown"],
            "market_price_target": formatted_mc["price_target"],
        }

    def optimize_context_for_tokens(self, tickers_data: dict[str, dict[str, Any]]) -> str:
        parts = [BATCH_TEMPLATE_HEADER, ""]
        for ticker, data in tickers_data.items():
            ctx = self._build_ticker_context(
                ticker, data["earnings"], data["news"], data.get("market_context")
            )
            parts.append(
                (
                    f"{ctx['ticker']} (Sector Expert: {ctx['expert_type']}, "
                    f"Industry: {ctx['industry']}):\n"
                    f"EPS: Est {ctx['eps_est']} vs Actual {ctx['eps_act']} "
                    f"(surprise: {ctx['eps_surprise']})\n"
                    f"Revenue: Est {ctx['rev_est']} vs Actual {ctx['rev_act']} "
                    f"(surprise: {ctx['rev_surprise']})\n"
                    f"Wall Street Context: {ctx['market_context']}\n"
                    f"News Headlines:\n{ctx['news']}\n"
                    f"Guidance & Strategic Context: {ctx['guidance']}\n"
                )
            )
        return "\n".join(parts)

    def _disabled_insights(self) -> dict[str, str]:
        return {
            "summary": "AI insights disabled - set OPENAI_API_KEY to enable",
            "strategic_analysis": "",
            "guidance_outlook": "",
            "risk_factors": "",
            "analyst_conclusion": "",
            "investment_recommendation": "N/A",
            "expert_recommendation": "General Financial Analyst",
        }

    def _blank_insight(self, ticker: str) -> dict[str, str]:
        return {
            "summary": "",
            "strategic_analysis": "",
            "guidance_outlook": "",
            "risk_factors": "",
            "analyst_conclusion": "",
            "investment_recommendation": "HOLD (Medium Confidence)",
            "expert_recommendation": self.get_company_sector(ticker),
        }

    def parse_structured_insights(
        self, response_text: str, tickers: list[str]
    ) -> dict[str, dict[str, str]]:
        results = {ticker: self._blank_insight(ticker) for ticker in tickers}
        if not response_text:
            return results

        ticker_lookup = {ticker.lower(): ticker for ticker in tickers}
        current_ticker: str | None = tickers[0] if len(tickers) == 1 else None
        current_section: str | None = None
        current_content: list[str] = []
        saw_ticker_header = False

        def flush_section() -> None:
            nonlocal current_content
            if current_ticker and current_section and current_content:
                results[current_ticker][current_section] = " ".join(current_content)
                current_content = []

        for raw in response_text.splitlines():
            line = raw.strip()
            if not line:
                flush_section()
                continue

            upper = line.upper()

            ticker_from_line: str | None = None
            if upper.startswith("TICKER:"):
                raw_name = line.split(":", 1)[1].strip().lower()
                ticker_from_line = ticker_lookup.get(raw_name)
                if not ticker_from_line and raw_name:
                    for low_name, canonical in ticker_lookup.items():
                        if low_name in raw_name or raw_name in low_name:
                            ticker_from_line = canonical
                            break
            else:
                candidate = line.rstrip(":").strip().lower()
                if candidate in ticker_lookup and line.rstrip().endswith(":"):
                    ticker_from_line = ticker_lookup[candidate]

            if ticker_from_line:
                flush_section()
                current_section = None
                current_content = []
                saw_ticker_header = True
                current_ticker = ticker_from_line
                continue

            if "EXECUTIVE SUMMARY" in upper:
                flush_section()
                current_section, current_content = "summary", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "STRATEGIC ANALYSIS" in upper:
                flush_section()
                current_section, current_content = "strategic_analysis", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "RISK FACTORS" in upper or "RISK FACTOR" in upper:
                flush_section()
                current_section, current_content = "risk_factors", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "GUIDANCE OUTLOOK" in upper:
                flush_section()
                current_section, current_content = "guidance_outlook", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "ANALYST CONCLUSION" in upper:
                flush_section()
                current_section, current_content = "analyst_conclusion", []
                if ":" in line:
                    content = line.split(":", 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif "INVESTMENT RECOMMENDATION" in upper:
                flush_section()
                if current_ticker and ":" in line:
                    value = line.split(":", 1)[1].strip()
                    if value:
                        results[current_ticker]["investment_recommendation"] = value
                current_section = None
            elif "EXPERT RECOMMENDATION" in upper:
                flush_section()
                if current_ticker and ":" in line:
                    value = line.split(":", 1)[1].strip()
                    if value:
                        results[current_ticker]["expert_recommendation"] = value
                current_section = None
            elif current_section and current_ticker:
                current_content.append(line)

        flush_section()

        if len(tickers) == 1 and not saw_ticker_header:
            single = results[tickers[0]]
            if not single["summary"] and not single["strategic_analysis"]:
                single["summary"] = response_text[:500]

        return results

    @staticmethod
    def _insights_incomplete(insights: dict[str, dict[str, str]]) -> bool:
        return any(
            not insight.get("summary") and not insight.get("strategic_analysis")
            for insight in insights.values()
        )

    def generate_ai_insights_single(
        self,
        ticker: str,
        earnings_data: dict[str, Any],
        news_data: list[dict[str, Any]],
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        if not self.openai.is_enabled:
            return self._disabled_insights()

        cache_key = f"{ticker}_{earnings_data.get('epsActual', 'N/A')}"
        if cache_key in self.insights_cache:
            return self.insights_cache[cache_key]

        expert_type = self.get_company_sector(ticker)
        ctx = self._build_ticker_context(ticker, earnings_data, news_data, market_context)
        context = SINGLE_TICKER_TEMPLATE.format(**ctx)

        try:
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=900,
            )
            parsed = self.parse_structured_insights(content, [ticker]).get(
                ticker, self._blank_insight(ticker)
            )
            self.insights_cache[cache_key] = parsed
            return parsed
        except Exception as exc:
            return {
                "summary": f"AI insights unavailable: {exc}",
                "strategic_analysis": "",
                "guidance_outlook": "",
                "risk_factors": "",
                "analyst_conclusion": "",
                "investment_recommendation": "N/A",
                "expert_recommendation": expert_type,
            }

    def generate_individual_insights(self, tickers_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
        insights: dict[str, dict[str, str]] = {}
        for i, (ticker, data) in enumerate(tickers_data.items()):
            insights[ticker] = self.generate_ai_insights_single(
                ticker,
                data["earnings"],
                data["news"],
                data.get("market_context"),
            )
            if i < len(tickers_data) - 1:
                time.sleep(random.uniform(10, 15))
        return insights

    def generate_batched_ai_insights(self, tickers_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
        if not self.openai.is_enabled:
            return {ticker: self._disabled_insights().copy() for ticker in tickers_data}

        def primary() -> dict[str, dict[str, str]]:
            context = self.optimize_context_for_tokens(tickers_data)
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=900 * max(len(tickers_data), 1),
            )
            parsed = self.parse_structured_insights(content, list(tickers_data.keys()))
            if self._insights_incomplete(parsed):
                return self.generate_individual_insights(tickers_data)
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

    @staticmethod
    def _beat_miss(actual_raw: Any, estimate_raw: Any) -> tuple[str, str]:
        """Return (badge_text, badge_kind) comparing actual vs estimate."""
        if actual_raw in (None, "N/A") or estimate_raw in (None, "N/A"):
            return ("", "neutral")
        try:
            actual = float(actual_raw)
            estimate = float(estimate_raw)
        except (ValueError, TypeError):
            return ("", "neutral")
        if actual > estimate:
            return ("Beat", "up")
        if actual < estimate:
            return ("Miss", "down")
        return ("Inline", "neutral")

    @staticmethod
    def _parse_recommendation(raw: str) -> dict[str, str]:
        text = raw.strip()
        if not text or text.upper() == "N/A":
            return {"rating": "N/A", "confidence": "", "reasoning": ""}

        confidence = ""
        paren_match = re.search(r"\(([^)]+)\)", text)
        if paren_match:
            confidence = paren_match.group(1).strip()

        reasoning = ""
        for sep in (" - ", " – ", " — "):
            if sep in text:
                reasoning = text.split(sep, 1)[1].strip()
                break

        upper = text.upper()
        rating = "HOLD"
        for candidate in ("STRONG BUY", "STRONG SELL", "BUY", "HOLD", "SELL", "N/A"):
            if upper.startswith(candidate):
                rating = candidate
                break
        else:
            for candidate in ("STRONG BUY", "STRONG SELL", "BUY", "HOLD", "SELL"):
                if candidate in upper:
                    rating = candidate
                    break

        return {"rating": rating, "confidence": confidence, "reasoning": reasoning}

    @staticmethod
    def _recommendation_badge_kind(rating: str) -> str:
        normalized = rating.upper()
        if normalized in ("STRONG BUY", "BUY"):
            return "up"
        if normalized in ("STRONG SELL", "SELL"):
            return "down"
        return "neutral"

    def _format_wall_street_body(self, market_context: dict[str, Any] | None) -> str:
        if not market_context:
            return ""
        formatted = self._format_market_context(
            market_context.get("trends", []),
            market_context.get("price_target", {}),
        )
        if formatted["breakdown"] == "N/A" and formatted["price_target"] == "N/A":
            return ""
        body = ""
        if formatted["breakdown"] != "N/A":
            body += et.key_value("Analyst Breakdown", formatted["breakdown"])
        if formatted["price_target"] != "N/A":
            body += et.key_value("Price Target", formatted["price_target"])
        return body

    def create_email_content(
        self,
        ticker: str,
        earnings_data: dict[str, Any],
        news_data: list[dict[str, Any]],
        ai_insights: dict[str, str],
        market_context: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        eps_est_raw = earnings_data.get("epsEstimate")
        eps_act_raw = earnings_data.get("epsActual")
        rev_est_raw = earnings_data.get("revenueEstimate")
        rev_act_raw = earnings_data.get("revenueActual")

        eps_est = self._format_number(eps_est_raw)
        eps_act = self._format_number(eps_act_raw)
        rev_est = self._format_revenue(rev_est_raw)
        rev_act = self._format_revenue(rev_act_raw)

        eps_badge_text, eps_badge_kind = self._beat_miss(eps_act_raw, eps_est_raw)
        rev_badge_text, rev_badge_kind = self._beat_miss(rev_act_raw, rev_est_raw)

        eps_surprise = self._surprise_pct(eps_act_raw, eps_est_raw)
        rev_surprise = self._surprise_pct(rev_act_raw, rev_est_raw)
        eps_surprise_line = f"{eps_surprise} vs est." if eps_surprise != "N/A" else ""
        rev_surprise_line = f"{rev_surprise} vs est." if rev_surprise != "N/A" else ""

        summary = ai_insights.get("summary", "No summary available")
        strategic = ai_insights.get("strategic_analysis", "")
        guidance = ai_insights.get("guidance_outlook", "")
        risks = ai_insights.get("risk_factors", "")
        conclusion = ai_insights.get("analyst_conclusion", "")
        recommendation = ai_insights.get("investment_recommendation", "HOLD (Medium Confidence)")
        expert = ai_insights.get("expert_recommendation", "General Financial Analyst")

        parsed_rec = self._parse_recommendation(recommendation)
        verdict_body = et.verdict_block(
            rating=parsed_rec["rating"],
            confidence=parsed_rec["confidence"],
            expert=expert,
            conclusion=conclusion,
            reasoning=parsed_rec["reasoning"],
            badge_kind=self._recommendation_badge_kind(parsed_rec["rating"]),
        )

        metrics_body = et.metric_row(
            et.metric_tile(
                "EPS", eps_act, eps_est, eps_badge_text, eps_badge_kind, eps_surprise_line
            ),
            et.metric_tile(
                "Revenue", rev_act, rev_est, rev_badge_text, rev_badge_kind, rev_surprise_line
            ),
        )

        analysis_sections: list[str] = []
        if summary and self._is_meaningful_summary(summary):
            analysis_sections.append(et.section("Executive Summary", summary))
        if strategic:
            analysis_sections.append(et.section("Strategic Analysis", strategic))
        if guidance:
            analysis_sections.append(et.section("Guidance Outlook", guidance))
        if risks:
            analysis_sections.append(et.section("Risk Factors", risks))
        if analysis_sections:
            analysis_body = "".join(analysis_sections)
        else:
            analysis_body = et.section("Analysis", "No insights available.")

        news_body = "".join(
            et.news_item(item.get("headline", "N/A"), item.get("url", "#"))
            for item in news_data[:3]
        )

        wall_street_body = self._format_wall_street_body(market_context)

        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        blocks: list[str] = [
            et.header(ticker, "Earnings Report"),
            et.card(verdict_body, title="Verdict"),
            et.card(metrics_body, title="Financial Results"),
            et.card(analysis_body, title="Analysis"),
        ]
        if wall_street_body:
            blocks.append(et.card(wall_street_body, title="Wall Street View"))
        if news_data:
            blocks.append(et.card(news_body, title="Recent News"))
        blocks.append(et.footer(f"Generated on {generated}"))

        html_content = et.page(f"{ticker} Earnings Report", blocks)

        plain_news = "\n".join([f"- {item.get('headline', 'N/A')}" for item in news_data[:3]])
        plain_wall_street = ""
        if wall_street_body:
            formatted = self._format_market_context(
                (market_context or {}).get("trends", []),
                (market_context or {}).get("price_target", {}),
            )
            plain_wall_street = f"""
WALL STREET VIEW
----------------
Analyst Breakdown: {formatted['breakdown']}
Price Target: {formatted['price_target']}
"""

        plain_content = f"""
{ticker} EARNINGS REPORT
======================

VERDICT
-------
Rating: {parsed_rec['rating']}
Confidence: {parsed_rec['confidence'] or 'N/A'}
Expert: {expert}

Analyst Conclusion:
{conclusion or 'No conclusion available'}

Reasoning:
{parsed_rec['reasoning'] or 'N/A'}

FINANCIAL RESULTS
-----------------
EPS: {eps_est} -> {eps_act} ({eps_surprise_line or 'N/A'})
Revenue: {rev_est} -> {rev_act} ({rev_surprise_line or 'N/A'})

ANALYSIS
--------
EXECUTIVE SUMMARY:
{summary}

STRATEGIC ANALYSIS:
{strategic or 'No strategic analysis available'}

GUIDANCE OUTLOOK:
{guidance or 'No guidance outlook available'}

RISK FACTORS:
{risks or 'No risk factors identified'}
{plain_wall_street}
RECENT NEWS
-----------
{plain_news}

Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        plain_content = re.sub(r"<[^>]+>", "", plain_content)
        return html_content, plain_content

    def _date_range(self, start_date: str, end_date: str) -> list[str]:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if end < start:
            start, end = end, start
        dates: list[str] = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return dates

    def _run_for_date(self, target_date: str, *, include_date_in_subject: bool = False) -> int:
        print(f"📅 Checking earnings for: {target_date}")

        tickers = load_tickers(self.settings.watchlist_csv)
        if not tickers:
            print("❌ No tickers loaded. Exiting.")
            return 0

        tickers_data: dict[str, dict[str, Any]] = {}
        for i, ticker in enumerate(tickers, 1):
            print(f"--- Processing {ticker} ({i}/{len(tickers)}) ---")
            earnings = self.finnhub.get_earnings_calendar(ticker, target_date)
            if not earnings:
                continue
            news = self.finnhub.get_company_news(ticker, target_date)
            trends = self.finnhub.get_recommendation_trends(ticker)
            price_target = self.finnhub.get_price_target(ticker)
            tickers_data[ticker] = {
                "earnings": earnings,
                "news": news,
                "market_context": {"trends": trends, "price_target": price_target},
            }

        if not tickers_data:
            print(f"ℹ️ No earnings data found for {target_date}.")
            return 0

        ai_insights = self.generate_batched_ai_insights(tickers_data)
        emails_sent = 0
        for ticker, data in tickers_data.items():
            subject = (
                f"{ticker} Earnings Report ({target_date})"
                if include_date_in_subject
                else f"{ticker} Earnings Report"
            )
            ticker_insights = ai_insights.get(ticker, {})
            html_content, plain_content = self.create_email_content(
                ticker=ticker,
                earnings_data=data["earnings"],
                news_data=data["news"],
                ai_insights=ticker_insights,
                market_context=data.get("market_context"),
            )
            if self.email_sender.send(subject, html_content, plain_content):
                emails_sent += 1

        print(f"✅ Sent {emails_sent} emails for {target_date}")
        return emails_sent

    def run(
        self,
        test_mode: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        print("🚀 Starting Earnings Agent")

        if start_date:
            end = end_date or datetime.now().strftime("%Y-%m-%d")
            dates = self._date_range(start_date, end)
            print(f"📆 Date range: {dates[0]} → {dates[-1]} ({len(dates)} days)")
            total_sent = 0
            for target_date in dates:
                total_sent += self._run_for_date(
                    target_date, include_date_in_subject=len(dates) > 1
                )
            print(f"🎉 Processing complete! Sent {total_sent} emails across {len(dates)} days")
            return

        target_date = (
            (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
            if test_mode
            else (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        )
        sent = self._run_for_date(target_date)
        if sent == 0:
            print("❌ No earnings data found. Exiting.")
        else:
            print(f"🎉 Processing complete! Sent {sent} emails for {target_date}")

