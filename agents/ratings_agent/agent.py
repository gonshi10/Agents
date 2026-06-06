"""Core analyst ratings agent implementation.

Alerts when Wall Street sentiment on a watchlist ticker shifts:
- Recommendation consensus (stateless): the latest monthly analyst-count period
  is compared against the prior period from a single ``/stock/recommendation``
  call. No persisted state is required.
- Price target (stateful): ``/stock/price-target`` is a current snapshot with no
  history, so the last-seen mean target is persisted to ``ratings_pt_snapshot``
  between runs (restored from GitHub Actions cache in CI) and compared.
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from common.clients.finnhub import FinnhubClient
from common.clients.openai_client import OpenAIClient
from common.config import Settings
from common.email import templates as et
from common.email.sender import EmailSender
from common.watchlist import load_tickers

from .prompts import BATCH_TEMPLATE_HEADER, SINGLE_TICKER_TEMPLATE, SYSTEM_PROMPT

# Detection thresholds.
REC_SCORE_THRESHOLD = 0.15  # min change in weighted consensus score to flag
PT_PCT_THRESHOLD = 5.0  # min |%| move in mean price target to flag


class RatingsAgent:
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

        self.snapshot_path = Path(settings.ratings_pt_snapshot)
        self.insights_cache: dict[str, dict[str, str]] = {}
        self.sector_cache: dict[str, str] = {}

        print("✓ Configuration loaded successfully")
        print("📊 Finnhub rate limiting enabled via shared client")
        if self.openai.is_enabled:
            print("✅ OpenAI SDK client initialized")
        else:
            print("⚠️ OpenAI API key not set - AI insights will be disabled")

    # ----- sector / expert mapping (mirrors earnings agent) -----

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

    # ----- change detection (pure functions, no network) -----

    @staticmethod
    def _consensus_score(period: dict[str, Any]) -> float | None:
        """Weighted consensus on a -2..+2 scale (higher = more bullish)."""
        try:
            strong_buy = float(period.get("strongBuy", 0) or 0)
            buy = float(period.get("buy", 0) or 0)
            hold = float(period.get("hold", 0) or 0)
            sell = float(period.get("sell", 0) or 0)
            strong_sell = float(period.get("strongSell", 0) or 0)
        except (ValueError, TypeError):
            return None
        total = strong_buy + buy + hold + sell + strong_sell
        if total <= 0:
            return None
        return (2 * strong_buy + buy - sell - 2 * strong_sell) / total

    def _detect_rec_change(self, trends: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Compare the two newest periods; flag an UPGRADE/DOWNGRADE on a material move."""
        if len(trends) < 2:
            return None
        latest, prior = trends[0], trends[1]
        score_latest = self._consensus_score(latest)
        score_prior = self._consensus_score(prior)
        if score_latest is None or score_prior is None:
            return None
        delta = score_latest - score_prior
        if abs(delta) < REC_SCORE_THRESHOLD:
            return None
        return {
            "direction": "UPGRADE" if delta > 0 else "DOWNGRADE",
            "score_before": round(score_prior, 2),
            "score_after": round(score_latest, 2),
            "period_before": prior.get("period", "N/A"),
            "period_after": latest.get("period", "N/A"),
            "breakdown": {
                "strongBuy": latest.get("strongBuy", 0),
                "buy": latest.get("buy", 0),
                "hold": latest.get("hold", 0),
                "sell": latest.get("sell", 0),
                "strongSell": latest.get("strongSell", 0),
            },
        }

    def _detect_pt_change(
        self, ticker: str, price_target: dict[str, Any], previous_pt: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        """Compare current mean price target against the last persisted snapshot."""
        try:
            current = price_target.get("targetMean")
            if current in (None, 0, "0"):
                return None
            current = float(current)
        except (ValueError, TypeError):
            return None

        prev_entry = previous_pt.get(ticker) or {}
        try:
            previous = prev_entry.get("targetMean")
            previous = float(previous) if previous not in (None, "") else None
        except (ValueError, TypeError):
            previous = None
        if not previous:
            return None  # no baseline yet — nothing to compare

        pct = (current - previous) / previous * 100.0
        if abs(pct) < PT_PCT_THRESHOLD:
            return None
        return {
            "direction": "RAISED" if pct > 0 else "CUT",
            "before": round(previous, 2),
            "after": round(current, 2),
            "pct": round(pct, 1),
        }

    # ----- snapshot persistence -----

    def _load_snapshot(self) -> dict[str, dict[str, Any]]:
        try:
            if self.snapshot_path.exists():
                with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"⚠️ Failed to load price-target snapshot: {exc}")
        return {}

    def _save_snapshot(self, data: dict[str, dict[str, Any]]) -> None:
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            print(f"✓ Price-target snapshot saved to {self.snapshot_path}")
        except Exception as exc:
            print(f"✗ Failed to save price-target snapshot: {exc}")

    # ----- AI insights (mirrors earnings agent shapes) -----

    def parse_structured_insights(self, response_text: str, ticker: str) -> dict[str, str]:
        result = {
            "summary": "",
            "rating_rationale": "",
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
            elif "RATING RATIONALE" in line.upper():
                if current_section and current_content:
                    result[current_section] = " ".join(current_content)
                current_section, current_content = "rating_rationale", []
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
        if not result["summary"] and not result["rating_rationale"]:
            result["summary"] = response_text[:500]
        return result

    def _disabled_insights(self) -> dict[str, str]:
        return {
            "summary": "AI insights disabled - set OPENAI_API_KEY to enable",
            "rating_rationale": "",
            "risk_factors": "",
            "investment_recommendation": "N/A",
            "expert_recommendation": "General Financial Analyst",
        }

    @staticmethod
    def _format_change(change: dict[str, Any]) -> dict[str, str]:
        """Flatten a change dict into prompt-ready strings."""
        rec = change.get("rec")
        pt = change.get("pt")
        if rec:
            change_type = f"Recommendation {rec['direction'].lower()}"
            rec_before = str(rec["score_before"])
            rec_after = str(rec["score_after"])
            breakdown = ", ".join(f"{k}={v}" for k, v in rec["breakdown"].items())
        else:
            change_type = "Price target move"
            rec_before = rec_after = "N/A"
            breakdown = "N/A"
        if pt:
            change_type += f" + price target {pt['direction'].lower()}"
            pt_before = f"${pt['before']}"
            pt_after = f"${pt['after']}"
            pt_pct = f"{pt['pct']:+}%"
        else:
            pt_before = pt_after = "N/A"
            pt_pct = "N/A"
        return {
            "change_type": change_type,
            "rec_before": rec_before,
            "rec_after": rec_after,
            "rec_breakdown": breakdown,
            "pt_before": pt_before,
            "pt_after": pt_after,
            "pt_pct": pt_pct,
        }

    def generate_ai_insights_single(self, ticker: str, change: dict[str, Any]) -> dict[str, str]:
        if not self.openai.is_enabled:
            return self._disabled_insights()

        expert_type = self.get_company_sector(ticker)
        fields = self._format_change(change)
        context = SINGLE_TICKER_TEMPLATE.format(
            ticker=ticker,
            expert_type=expert_type,
            change_type=fields["change_type"],
            rec_before=fields["rec_before"],
            rec_after=fields["rec_after"],
            rec_breakdown=fields["rec_breakdown"],
            pt_before=fields["pt_before"],
            pt_after=fields["pt_after"],
            pt_pct=fields["pt_pct"],
        )

        try:
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=600,
            )
            return self.parse_structured_insights(content, ticker)
        except Exception as exc:
            return {
                "summary": f"AI insights unavailable: {exc}",
                "rating_rationale": "",
                "risk_factors": "",
                "investment_recommendation": "N/A",
                "expert_recommendation": expert_type,
            }

    def generate_individual_insights(
        self, changes: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        insights: dict[str, dict[str, str]] = {}
        for i, (ticker, change) in enumerate(changes.items()):
            insights[ticker] = self.generate_ai_insights_single(ticker, change)
            if i < len(changes) - 1:
                time.sleep(random.uniform(10, 15))
        return insights

    def _build_batch_context(self, changes: dict[str, dict[str, Any]]) -> str:
        parts = [BATCH_TEMPLATE_HEADER, ""]
        for ticker, change in changes.items():
            expert_type = self.get_company_sector(ticker)
            fields = self._format_change(change)
            parts.append(
                (
                    f"{ticker} (Sector Expert: {expert_type}):\n"
                    f"Change: {fields['change_type']}\n"
                    f"Consensus: {fields['rec_before']} -> {fields['rec_after']} "
                    f"(latest breakdown: {fields['rec_breakdown']})\n"
                    f"Price target: {fields['pt_before']} -> {fields['pt_after']} "
                    f"({fields['pt_pct']})\n"
                )
            )
        return "\n".join(parts)

    def generate_batched_ai_insights(
        self, changes: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        if not self.openai.is_enabled:
            return {ticker: self._disabled_insights() for ticker in changes}

        def primary() -> dict[str, dict[str, str]]:
            context = self._build_batch_context(changes)
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=600 * max(len(changes), 1),
            )
            return {ticker: self.parse_structured_insights(content, ticker) for ticker in changes}

        return self.openai.run_with_fallback(
            primary, lambda: self.generate_individual_insights(changes)
        )

    # ----- email rendering -----

    @staticmethod
    def _change_banner(change: dict[str, Any]) -> str:
        rec = change.get("rec")
        pt = change.get("pt")
        bits: list[str] = []
        if rec:
            arrow = "⬆️" if rec["direction"] == "UPGRADE" else "⬇️"
            bits.append(
                f"{arrow} {rec['direction']}: consensus {rec['score_before']} → "
                f"{rec['score_after']} ({rec['period_before']} → {rec['period_after']})"
            )
        if pt:
            bits.append(
                f"🎯 Price target {pt['direction']}: ${pt['before']} → ${pt['after']} "
                f"({pt['pct']:+}%)"
            )
        return " | ".join(bits)

    @staticmethod
    def _change_badges(change: dict[str, Any]) -> list[str]:
        """Render the change as color-coded badges (direction drives the color)."""
        rec = change.get("rec")
        pt = change.get("pt")
        badges: list[str] = []
        if rec:
            kind = "up" if rec["direction"] == "UPGRADE" else "down"
            badges.append(
                et.badge(
                    f"{rec['direction']}: consensus {rec['score_before']} → {rec['score_after']}",
                    kind,
                )
            )
        if pt:
            kind = "up" if pt["direction"] == "RAISED" else "down"
            badges.append(
                et.badge(
                    f"Price target {pt['direction']}: ${pt['before']} → ${pt['after']} "
                    f"({pt['pct']:+}%)",
                    kind,
                )
            )
        return badges

    def create_email_content(
        self, ticker: str, change: dict[str, Any], ai_insights: dict[str, str]
    ) -> tuple[str, str]:
        banner = self._change_banner(change)
        summary = ai_insights.get("summary", "No summary available")
        rationale = ai_insights.get("rating_rationale", "")
        risks = ai_insights.get("risk_factors", "")
        recommendation = ai_insights.get("investment_recommendation", "HOLD (Medium Confidence)")
        expert = ai_insights.get("expert_recommendation", "General Financial Analyst")

        insight_sections: list[str] = []
        if summary:
            insight_sections.append(et.section("Executive Summary", summary))
        if rationale:
            insight_sections.append(et.section("Rating Rationale", rationale))
        if risks:
            insight_sections.append(et.section("Risk Factors", risks))
        if not insight_sections:
            insight_sections.append(et.section("AI Insights", "No insights available."))

        badges = self._change_badges(change)
        change_card = et.card(
            "".join(badges) if badges else et.esc(banner),
            title="What changed",
        )
        rec_card = et.card(
            et.key_value("Investment Recommendation", recommendation)
            + et.key_value("Expert", expert),
        )
        insights_card = et.card("".join(insight_sections), title="AI Insights")
        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html_content = et.page(
            f"{ticker} Analyst Rating Change",
            [
                et.header(f"{ticker} Analyst Rating Change"),
                change_card,
                rec_card,
                insights_card,
                et.footer(f"Generated on {generated}"),
            ],
        )

        plain_content = f"""
{ticker} ANALYST RATING CHANGE
==============================

{banner}

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

RATING RATIONALE:
{rationale or 'No rationale available'}

RISK FACTORS:
{risks or 'No risk factors identified'}

Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        plain_content = re.sub(r"<[^>]+>", "", plain_content)
        return html_content, plain_content

    # ----- main flow -----

    def run(self, test_mode: bool = False) -> None:
        print("🚀 Starting Ratings Agent")
        if test_mode:
            print("🧪 TEST_MODE on")

        tickers = load_tickers(self.settings.watchlist_csv)
        if not tickers:
            print("❌ No tickers loaded. Exiting.")
            return

        previous_pt = self._load_snapshot()
        current_pt: dict[str, dict[str, Any]] = {}
        changes: dict[str, dict[str, Any]] = {}

        for i, ticker in enumerate(tickers, 1):
            print(f"--- Processing {ticker} ({i}/{len(tickers)}) ---")
            try:
                trends = self.finnhub.get_recommendation_trends(ticker)
                rec_change = self._detect_rec_change(trends)

                price_target = self.finnhub.get_price_target(ticker)
                if price_target.get("targetMean") not in (None, 0, "0"):
                    current_pt[ticker] = {
                        "targetMean": price_target.get("targetMean"),
                        "lastUpdated": price_target.get("lastUpdated"),
                    }
                pt_change = self._detect_pt_change(ticker, price_target, previous_pt)

                if rec_change or pt_change:
                    changes[ticker] = {"rec": rec_change, "pt": pt_change}
                    print(f"  🔔 Change detected: {self._change_banner(changes[ticker])}")
            except Exception as exc:
                print(f"✗ Error processing {ticker}: {exc}")
                continue

        # Carry forward baselines for tickers we didn't refresh this run.
        for ticker, entry in previous_pt.items():
            current_pt.setdefault(ticker, entry)
        self._save_snapshot(current_pt)

        if not changes:
            print("✅ No rating changes detected. Nothing to send.")
            return

        ai_insights = self.generate_batched_ai_insights(changes)
        emails_sent = 0
        for ticker, change in changes.items():
            subject = f"{ticker} Analyst Rating Change"
            html_content, plain_content = self.create_email_content(
                ticker=ticker,
                change=change,
                ai_insights=ai_insights.get(ticker, {}),
            )
            if self.email_sender.send(subject, html_content, plain_content):
                emails_sent += 1

        print(f"🎉 Processing complete! Sent {emails_sent} emails for {len(changes)} changes")
