"""Core flights agent implementation.

Watches a CSV watchlist of flight routes and emails ONE digest when a fare is
worth knowing about. Two triggers:
- Target price (stateful): the fare newly crosses at or below a per-route
  ``MaxPrice`` — first run, or the prior snapshot was above the target.
- Price drop (stateful): the Aviasales Data API exposes only a current cheapest
  fare with no history, so the last-seen price is persisted to
  ``flights_price_snapshot`` between runs (restored from GitHub Actions cache in
  CI) and compared; a drop of >= ``flights_price_drop_pct`` flags.
"""

from __future__ import annotations

import json
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from common.clients.flights import TravelpayoutsClient
from common.clients.openai_client import OpenAIClient
from common.config import Settings
from common.email import templates as et
from common.email.sender import EmailSender
from common.watchlist import load_routes

from .prompts import BATCH_TEMPLATE_HEADER, SINGLE_ROUTE_TEMPLATE, SYSTEM_PROMPT


class FlightsAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
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

        self.drop_pct = settings.flights_price_drop_pct
        self.currency = settings.flights_currency
        self.snapshot_path = Path(settings.flights_price_snapshot)

        self.client = (
            TravelpayoutsClient(token=settings.flights_api_token)
            if settings.flights_api_token
            else None
        )

        print("✓ Configuration loaded successfully")
        if self.client:
            print("✈️ Travelpayouts client initialized")
        else:
            print("⚠️ FLIGHTS_API_TOKEN not set - flights agent will be a no-op")
        if self.openai.is_enabled:
            print("✅ OpenAI SDK client initialized")
        else:
            print("⚠️ OpenAI API key not set - AI insights will be disabled")

    # ----- route identity & change detection (pure functions, no network) -----

    @staticmethod
    def route_key(route: dict[str, Any]) -> str:
        key = f"{route['origin']}-{route['destination']}-{route['depart_month']}"
        if route.get("return_month"):
            key += f"-{route['return_month']}"
        if route.get("one_way"):
            key += "-ow"
        return key

    def detect_change(
        self,
        route: dict[str, Any],
        fare: dict[str, Any],
        prev: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Flag a route when the fare newly hits its target price or drops materially.

        Target alerts fire on transition into the below-target zone (first run or
        prior price above ``MaxPrice``). A drop needs a prior price to compare.
        """
        price = float(fare["price"])
        max_price = route.get("max_price")
        prev_price = None
        if prev:
            try:
                prev_price = float(prev.get("price")) if prev.get("price") not in (None, "") else None
            except (ValueError, TypeError):
                prev_price = None

        reasons: list[str] = []
        target_hit = max_price is not None and price <= max_price
        newly_at_target = target_hit and (
            prev_price is None or prev_price > max_price
        )
        if newly_at_target:
            reasons.append(f"At/below target ${max_price:.0f}")

        pct = None
        if prev_price:
            pct = (prev_price - price) / prev_price * 100.0
            if pct >= self.drop_pct:
                reasons.append(f"Dropped {pct:.0f}% (${prev_price:.0f} → ${price:.0f})")

        if not reasons:
            return None

        return {
            "route_key": self.route_key(route),
            "origin": route["origin"],
            "destination": route["destination"],
            "depart_month": route["depart_month"],
            "return_month": route.get("return_month"),
            "price": round(price, 2),
            "prev_price": round(prev_price, 2) if prev_price else None,
            "pct": round(pct, 1) if pct is not None else None,
            "airline": fare.get("airline", ""),
            "link": fare.get("link", ""),
            "reasons": reasons,
        }

    # ----- snapshot persistence -----

    def _load_snapshot(self) -> dict[str, dict[str, Any]]:
        try:
            if self.snapshot_path.exists():
                with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    return data if isinstance(data, dict) else {}
        except Exception as exc:
            print(f"⚠️ Failed to load price snapshot: {exc}")
        return {}

    def _save_snapshot(self, data: dict[str, dict[str, Any]]) -> None:
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            print(f"✓ Price snapshot saved to {self.snapshot_path}")
        except Exception as exc:
            print(f"✗ Failed to save price snapshot: {exc}")

    # ----- AI insights (mirrors ratings agent shapes) -----

    def parse_structured_insights(self, response_text: str) -> dict[str, str]:
        result = {"summary": "", "price_context": "", "booking_tip": ""}
        if not response_text:
            return result

        current_section: str | None = None
        current_content: list[str] = []

        def flush() -> None:
            if current_section and current_content:
                result[current_section] = " ".join(current_content)

        for raw in response_text.split("\n"):
            line = raw.strip()
            if not line:
                flush()
                current_content = []
                continue

            upper = line.upper()
            if "DEAL SUMMARY" in upper:
                flush()
                current_section, current_content = "summary", []
            elif "PRICE CONTEXT" in upper:
                flush()
                current_section, current_content = "price_context", []
            elif "BOOKING TIP" in upper:
                flush()
                current_section, current_content = "booking_tip", []
            else:
                if current_section:
                    current_content.append(line)
                continue

            if ":" in line:
                content = line.split(":", 1)[1].strip()
                if content:
                    current_content.append(content)

        flush()
        if not result["summary"]:
            result["summary"] = response_text[:500]
        return result

    def _disabled_insights(self) -> dict[str, str]:
        return {
            "summary": "AI insights disabled - set OPENAI_API_KEY to enable",
            "price_context": "",
            "booking_tip": "",
        }

    @staticmethod
    def _fmt_change_fields(change: dict[str, Any]) -> dict[str, str]:
        return_note = (
            f" (return {change['return_month']})" if change.get("return_month") else " (one-way)"
        )
        return {
            "origin": change["origin"],
            "destination": change["destination"],
            "depart_month": change["depart_month"],
            "return_note": return_note,
            "price": f"${change['price']:.0f} {change.get('airline') or ''}".strip(),
            "prev_price": f"${change['prev_price']:.0f}" if change.get("prev_price") else "N/A",
            "trigger": "; ".join(change.get("reasons", [])),
        }

    def generate_ai_insights_single(self, change: dict[str, Any]) -> dict[str, str]:
        if not self.openai.is_enabled:
            return self._disabled_insights()
        context = SINGLE_ROUTE_TEMPLATE.format(**self._fmt_change_fields(change))
        try:
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT, user_prompt=context, max_tokens=400
            )
            return self.parse_structured_insights(content)
        except Exception as exc:
            return {"summary": f"AI insights unavailable: {exc}", "price_context": "", "booking_tip": ""}

    def generate_individual_insights(
        self, changes: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        insights: dict[str, dict[str, str]] = {}
        items = list(changes.items())
        for i, (key, change) in enumerate(items):
            insights[key] = self.generate_ai_insights_single(change)
            if i < len(items) - 1:
                time.sleep(random.uniform(10, 15))
        return insights

    def _build_batch_context(self, changes: dict[str, dict[str, Any]]) -> str:
        parts = [BATCH_TEMPLATE_HEADER, ""]
        for change in changes.values():
            fields = self._fmt_change_fields(change)
            parts.append(
                f"{fields['origin']} -> {fields['destination']} ({fields['depart_month']}"
                f"{fields['return_note']}):\n"
                f"Current fare: {fields['price']}\n"
                f"Previous fare: {fields['prev_price']}\n"
                f"Trigger: {fields['trigger']}\n"
            )
        return "\n".join(parts)

    def generate_batched_ai_insights(
        self, changes: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, str]]:
        if not self.openai.is_enabled:
            return {key: self._disabled_insights() for key in changes}

        def primary() -> dict[str, dict[str, str]]:
            context = self._build_batch_context(changes)
            content = self.openai.complete(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=context,
                max_tokens=400 * max(len(changes), 1),
            )
            # The batch response is not reliably segmented per-route, so apply the
            # same parsed insight to each route; per-route fallback runs on failure.
            parsed = self.parse_structured_insights(content)
            return {key: dict(parsed) for key in changes}

        return self.openai.run_with_fallback(
            primary, lambda: self.generate_individual_insights(changes)
        )

    # ----- email rendering -----

    def create_digest_email(
        self, changes: dict[str, dict[str, Any]], insights: dict[str, dict[str, str]]
    ) -> tuple[str, str, str]:
        n = len(changes)
        subject = f"✈️ {n} flight price alert{'s' if n != 1 else ''}"

        html_cards: list[str] = []
        plain_blocks: list[str] = []
        for key, change in changes.items():
            ins = insights.get(key, {})
            route = f"{change['origin']} → {change['destination']}"
            when = change["depart_month"] + (
                f" / {change['return_month']}" if change.get("return_month") else " (one-way)"
            )
            reasons = "; ".join(change.get("reasons", []))
            airline = change.get("airline") or "N/A"
            summary = ins.get("summary", "")
            price_context = ins.get("price_context", "")
            booking_tip = ins.get("booking_tip", "")
            link = change.get("link") or ""

            reason_badges = "".join(
                et.badge(r, "up") for r in change.get("reasons", [])
            )
            meta = et.key_value("When", when) + et.key_value("Airline", airline)

            ai_html = ""
            if summary:
                ai_html += et.section("Deal Summary", summary)
            if price_context:
                ai_html += et.section("Price Context", price_context)
            if booking_tip:
                ai_html += et.section("Booking Tip", booking_tip)

            book_link = et.link_button("Book on Aviasales", link) if link else ""
            card_body = reason_badges + meta + ai_html + book_link
            html_cards.append(
                et.card(card_body, title=f"{route} — ${change['price']:.0f}")
            )

            plain_blocks.append(
                f"{route} — ${change['price']:.0f}\n"
                f"  {when} | {airline} | {reasons}\n"
                + (f"  {summary}\n" if summary else "")
                + (f"  Price context: {price_context}\n" if price_context else "")
                + (f"  Tip: {booking_tip}\n" if booking_tip else "")
                + (f"  Book: {link}\n" if link else "")
            )

        generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_content = et.page(
            "Flight Price Alerts",
            [
                et.header(
                    "✈️ Flight Price Alerts",
                    f"{n} route{'s' if n != 1 else ''} worth a look",
                ),
                *html_cards,
                et.footer(f"Generated on {generated} · fares via Aviasales (last 48h)"),
            ],
        )
        plain_content = (
            "FLIGHT PRICE ALERTS\n===================\n\n"
            + "\n".join(plain_blocks)
            + f"\nGenerated on {generated} · fares via Aviasales (last 48h)\n"
        )
        plain_content = re.sub(r"<[^>]+>", "", plain_content)
        return subject, html_content, plain_content

    # ----- main flow -----

    def run(self, test_mode: bool = False) -> None:
        print("🚀 Starting Flights Agent")
        if test_mode:
            print("🧪 TEST_MODE on")

        if not self.client:
            print("❌ FLIGHTS_API_TOKEN not set. Exiting.")
            return

        routes = load_routes(self.settings.flights_watchlist_csv)
        if not routes:
            print("❌ No routes loaded. Exiting.")
            return

        previous = self._load_snapshot()
        current: dict[str, dict[str, Any]] = {}
        changes: dict[str, dict[str, Any]] = {}

        for i, route in enumerate(routes, 1):
            key = self.route_key(route)
            print(f"--- Processing {route['origin']}→{route['destination']} ({i}/{len(routes)}) ---")
            try:
                fare = self.client.get_cheapest_fare(
                    origin=route["origin"],
                    destination=route["destination"],
                    depart_month=route["depart_month"],
                    return_month=route.get("return_month"),
                    one_way=route.get("one_way", False),
                    currency=self.currency,
                )
                if not fare:
                    print("  (no fare found)")
                    continue

                current[key] = {
                    "price": fare["price"],
                    "airline": fare.get("airline", ""),
                    "departure_at": fare.get("departure_at", ""),
                    "found_at": datetime.now().isoformat(timespec="seconds"),
                }

                change = self.detect_change(route, fare, previous.get(key))
                if change:
                    changes[key] = change
                    print(f"  🔔 {'; '.join(change['reasons'])}")
            except Exception as exc:
                print(f"✗ Error processing {key}: {exc}")
                continue

        # Carry forward baselines for routes we didn't refresh this run.
        for key, entry in previous.items():
            current.setdefault(key, entry)
        self._save_snapshot(current)

        if not changes:
            print("✅ No flight alerts to send.")
            return

        insights = self.generate_batched_ai_insights(changes)
        subject, html_content, plain_content = self.create_digest_email(changes, insights)
        if self.email_sender.send(subject, html_content, plain_content):
            print(f"🎉 Sent 1 digest email covering {len(changes)} route alert(s)")
        else:
            print("✗ Failed to send digest email")
