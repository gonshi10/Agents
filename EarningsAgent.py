#!/usr/bin/env python3
"""
Earnings Watchlist Agent — Midnight ET, CSV-only, No DB, WITH PRESS-RELEASE TEXT
- Runs once per ET midnight (script self-guards to only send at ~00:xx ET)
- Reads tickers from watchlist.csv (Symbol column)
- Sends ONE email per ticker that reported during the ET day that just ended
- Includes EPS/Revenue actual vs estimate, guidance/forecast (from PR/call text when available), headlines,
  and AI bullet points (5–8) based on full press-release/IR text if accessible.

Env vars (set via GitHub Actions Secrets or local .env):
FINNHUB_API_KEY=...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=your_app_password
EMAIL_TO=your@gmail.com
WATCHLIST_CSV=./watchlist.csv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
"""

import csv
import html
import os
import re
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple
import requests
from zoneinfo import ZoneInfo

# ----- DEBUG Vars -----
LOCAL = False
if LOCAL:
    from dotenv import load_dotenv
    load_dotenv()
TEST = True
# ----------------------

FINNHUB_BASE = "https://finnhub.io/api/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# ---------- small HTML helpers ----------
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
NEWLINE_RE = re.compile(r"\n{3,}")

def strip_html(raw: str) -> str:
    text = TAG_RE.sub("\n", raw)
    text = WHITESPACE_RE.sub(" ", text)
    text = NEWLINE_RE.sub("\n\n", text)
    return text.strip()

def extract_article_maintext(html_text: str) -> str:
    """
    Very simple main-text extractor (no external libs).
    Tries common containers first; falls back to concatenated <p> text.
    """
    lowered = html_text.lower()

    # Try to isolate likely article containers
    blocks = []
    # Common PR/article wrappers
    for marker in [
        r"<article[^>]*>.*?</article>",
        r"<div[^>]+class=[\"'][^\"']*(?:article|entry|post|content|story|pr|press)[^\"']*[\"'][^>]*>.*?</div>",
        r"<section[^>]+class=[\"'][^\"']*(?:article|content|story)[^\"']*[\"'][^>]*>.*?</section>",
    ]:
        for m in re.finditer(marker, lowered, flags=re.DOTALL):
            blocks.append(html_text[m.start():m.end()])

    # Fallback: grab many <p> tags as a block
    if not blocks:
        p_texts = re.findall(r"<p[^>]*>.*?</p>", html_text, flags=re.DOTALL | re.IGNORECASE)
        if p_texts:
            blocks = ["\n".join(p_texts)]

    if not blocks:
        return ""

    # Choose the largest block by text length
    best = max(blocks, key=lambda b: len(b))
    # Strip script/style
    best = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", best, flags=re.DOTALL | re.IGNORECASE)
    # Remove nav/aside bits if embedded
    best = re.sub(r"<(aside|nav|footer|header)[^>]*>.*?</\1>", "", best, flags=re.DOTALL | re.IGNORECASE)

    return strip_html(best)

# ---------- env + CSV ----------
def env(name: str, default: Optional[str] = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

def load_tickers(csv_path: str) -> List[str]:
    tickers = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
            if sym:
                tickers.append(sym)
    if not tickers:
        raise RuntimeError("No tickers found in CSV. Ensure it has a 'Symbol' header.")
    return sorted(set(tickers))

# ---------- finnhub ----------
def fh_get(path: str, params: dict, key: str) -> dict:
    p = {"token": key, **params}
    r = requests.get(f"{FINNHUB_BASE}{path}", params=p, timeout=30, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.json()

def get_earnings_for_et_day(ticker: str, finnhub_key: str, et_day_str: str) -> list:
    data = fh_get("/calendar/earnings", {"from": et_day_str, "to": et_day_str, "symbol": ticker}, finnhub_key)
    return data.get("earningsCalendar", []) or []

def get_company_news_for_et_day(ticker: str, finnhub_key: str, et_day_str: str) -> list:
    data = fh_get("/company-news", {"symbol": ticker, "from": et_day_str, "to": et_day_str}, finnhub_key)
    out = []
    for n in data or []:
        headline = (n.get("headline") or "").strip()
        src = (n.get("source") or "").strip().lower()
        url = (n.get("url") or "").strip()
        # prioritize press-release style sources/domains
        is_prish = any(d in url.lower() for d in [
            "businesswire.com", "prnewswire.com", "globenewswire.com", "newsfilecorp.com",
            "seekingalpha.com", "investor", "ir.", "/press-", "/pressrelease", "sec.gov", "8-k"
        ])
        if re.search(r"\b(Q[1-4]|quarter|earnings|results|guidance|outlook|forecast)\b", headline, re.I) or is_prish:
            out.append(n)
    # newest first
    out.sort(key=lambda x: x.get("datetime", 0), reverse=True)
    return out[:10]

# ---------- fetch press text ----------
def fetch_press_text(url: str) -> str:
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        r.raise_for_status()
        text = extract_article_maintext(r.text)
        # trim super long content for LLM prompt safety
        if len(text) > 8000:
            text = text[:8000] + "\n[...]"
        return text
    except Exception:
        return ""

# ---------- guidance extraction (regex heuristics from PR/summary) ----------
def extract_guidance_lines_from_text(text: str) -> List[str]:
    lines: List[str] = []
    # Common guidance patterns
    patterns: List[Tuple[str, re.Pattern]] = [
        ("Revenue", re.compile(
            r"(?:revenue|sales).{0,40}(?:guidance|outlook|expects|forecast|sees).{0,40}\$?\s*([0-9][0-9,\.]*)\s*(?:to|-|–|—)\s*\$?\s*([0-9][0-9,\.]*)",
            re.I)),
        ("Revenue", re.compile(
            r"(?:revenue|sales).{0,40}(?:guidance|outlook|expects|forecast|sees).{0,40}\$?\s*([0-9][0-9,\.]*)",
            re.I)),
        ("EPS", re.compile(
            r"(?:EPS|earnings per share).{0,40}(?:guidance|outlook|expects|forecast|sees).{0,40}\$?\s*(-?[0-9][0-9\.,]*)(?:\s*(?:to|-|–|—)\s*\$?\s*(-?[0-9][0-9\.,]*))?",
            re.I)),
        ("Margin", re.compile(
            r"(?:margin|GM|operating margin).{0,40}(?:guidance|outlook|expects|forecast|sees).{0,40}([0-9]{1,3}\.?[0-9]?)\s*%",
            re.I)),
        ("Growth", re.compile(
            r"(?:growth|increase|decline).{0,30}(?:guidance|outlook|expects|forecast|sees).{0,30}([0-9]{1,3}\.?[0-9]?)\s*%",
            re.I)),
    ]
    for label, pat in patterns:
        for m in pat.finditer(text):
            if m.lastindex == 2 and m.group(2):
                a, b = m.group(1), m.group(2)
                lines.append(f"{label} guidance: {a}–{b}")
            else:
                lines.append(f"{label} guidance: {m.group(1)}")

    # Period identifiers
    for m in re.finditer(r"\b(FY\s?20\d{2}|fiscal\s+(?:year|quarter|Q[1-4]))\b", text, re.I):
        val = m.group(1).strip()
        if val and all(val not in l for l in lines):
            lines.append(f"Guidance period mention: {val}")

    # de-dup, cap
    dedup, seen = [], set()
    for l in lines:
        if l not in seen:
            dedup.append(l)
            seen.add(l)
    return dedup[:8]

# ---------- AI summarization ----------
SUMMARY_SYSTEM_PROMPT = (
    "You are an equity research assistant. Write a crisp, investor-grade daily recap for a single ticker's "
    "quarterly report that occurred today (US Eastern). Return 5–8 short bullet points covering: "
    "(1) headline results vs estimates (EPS/revenue), "
    "(2) YoY/Seq color if available, "
    "(3) explicit guidance/outlook (forecasts) with numbers/ranges if present, "
    "(4) key drivers (segments/geos), and "
    "(5) likely implications (bull/bear). Keep it neutral, specific, and concise."
)

def _coerce_float(x):
    try:
        return float(x)
    except Exception:
        return None

def build_facts_for_llm(ticker: str, period, eps_est, eps_act, rev_est, rev_act,
                        guidance_lines: List[str], news: list, press_texts: List[str]) -> str:
    lines = [f"Ticker: {ticker}", f"Period: {period}"]
    if _coerce_float(eps_act) is not None or _coerce_float(eps_est) is not None:
        lines.append(f"EPS: actual={eps_act} estimate={eps_est}")
    if _coerce_float(rev_act) is not None or _coerce_float(rev_est) is not None:
        lines.append(f"Revenue: actual={rev_act} estimate={rev_est}")
    if guidance_lines:
        lines.append("Extracted guidance (regex):")
        for g in guidance_lines:
            lines.append(f"- {g}")
    if news:
        lines.append("Links:")
        for n in news[:5]:
            headline = (n.get("headline") or "").strip()
            src = (n.get("source") or "").strip()
            url = (n.get("url") or "").strip()
            lines.append(f"- {headline} [{src}] {url}")
    # Append short press excerpts
    if press_texts:
        lines.append("Press release excerpts (for grounding):")
        for t in press_texts[:2]:
            excerpt = t.strip().split("\n")
            excerpt = " ".join(excerpt[:12])  # ~ first few sentences
            if len(excerpt) > 1200:
                excerpt = excerpt[:1200] + " [...]"
            lines.append(f"- {excerpt}")
    return "\n".join(lines)

def summarize_with_llm(openai_api_key: str, model: str, facts_text: str) -> str:
    headers = {"Authorization": f"Bearer {openai_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": facts_text},
        ],
        "temperature": 0.25,
    }
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()

# ---------- email ----------
def send_email(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
               email_to: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = email_to
    msg["Subject"] = subject

    text_body = re.sub(r"<[^>]+>", "", html_body)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_pass)
        s.send_message(msg)

# ---------- misc formatting ----------
def fmt_num(x) -> str:
    if x in (None, "", "null"):
        return "—"
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)

# ---------- main ----------
def main():
    # Only act during 00:xx in New York
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.hour != 0 and not TEST:
        print(f"[INFO] Not midnight ET (now_et={now_et}); exiting.")
        return

    # The ET day that just ended
    target_et_day = (now_et - timedelta(days=1)).date()
    et_day_str = target_et_day.isoformat()

    finnhub_key = env("FINNHUB_API_KEY")
    tickers = load_tickers(env("WATCHLIST_CSV", "./watchlist.csv"))

    smtp_host = env("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(env("SMTP_PORT", "587"))
    smtp_user = env("SMTP_USER")
    smtp_pass = env("SMTP_PASS")
    email_to = env("EMAIL_TO")

    openai_key = os.getenv("OPENAI_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    sent_any = False

    for t in tickers:
        try:
            events = get_earnings_for_et_day(t, finnhub_key, et_day_str)
        except Exception as e:
            print(f"[WARN] earnings fetch failed for {t}: {e}")
            continue

        for ev in events:
            period = ev.get("period") or ev.get("quarter") or et_day_str
            date_str = ev.get("date") or ev.get("reportDate") or et_day_str

            eps_est = ev.get("epsEstimate") or ev.get("estimate")
            eps_act = ev.get("epsActual") or ev.get("actual")
            rev_est = ev.get("revenueEstimate")
            rev_act = ev.get("revenueActual")

            # Pull same-day news, try to fetch full PR text for up to 2 links
            try:
                news = get_company_news_for_et_day(t, finnhub_key, et_day_str)
            except Exception as e:
                print(f"[WARN] news fetch failed for {t}: {e}")
                news = []

            press_texts: List[str] = []
            for n in news:
                url = (n.get("url") or "").strip()
                if not url:
                    continue
                # prefer PR-ish domains first, cap at 2 fetches
                if any(d in url.lower() for d in ["businesswire.com", "prnewswire.com", "globenewswire.com", "newsfilecorp.com", "investor", "ir."]):
                    press_texts.append(fetch_press_text(url))
                if len([p for p in press_texts if p]) >= 2:
                    break
            # if no PR domains found, try first non-empty
            if not any(press_texts):
                for n in news[:2]:
                    url = (n.get("url") or "").strip()
                    if url:
                        txt = fetch_press_text(url)
                        if txt:
                            press_texts.append(txt)
                    if len([p for p in press_texts if p]) >= 2:
                        break

            # Regex guidance from combined text (PR text + headlines/summaries)
            combined_text = "\n".join([(n.get("headline") or "") + " " + (n.get("summary") or "") for n in news])
            combined_text += "\n" + "\n".join(press_texts)
            guidance_lines = extract_guidance_lines_from_text(combined_text)

            # LLM summary
            if openai_key:
                try:
                    facts_text = build_facts_for_llm(t, period, eps_est, eps_act, rev_est, rev_act, guidance_lines, news, press_texts)
                    bullets_md = summarize_with_llm(openai_key, openai_model, facts_text)
                    bullet_lines = [ln.strip("-• ").strip() for ln in bullets_md.splitlines() if ln.strip()]
                    summary_html = "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in bullet_lines) + "</ul>"
                except Exception as e:
                    summary_html = f"<p style='color:#777'>(AI summary unavailable: {html.escape(str(e))})</p>"
            else:
                summary_html = "<p style='color:#777'>(AI summary disabled — set OPENAI_API_KEY to enable.)</p>"

            # Headlines list
            news_items_html = "".join(
                f"<li><a href='{html.escape(n.get('url') or '')}'>{html.escape(n.get('headline') or '')}</a> "
                f"<em>({html.escape(n.get('source') or 'source')})</em></li>"
                for n in news
            ) or "<li>No matching news items</li>"

            # Guidance block
            if guidance_lines:
                guidance_html = "<ul>" + "".join(f"<li>{html.escape(g)}</li>" for g in guidance_lines) + "</ul>"
            else:
                guidance_html = "<p style='color:#777'>No explicit guidance found in the accessible text.</p>"

            html_body = f"""
            <html>
              <body style="font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height:1.45; color:#111;">
                <h2 style="margin:0 0 4px 0">{html.escape(t)} — Quarterly Results Recap</h2>
                <div style="color:#555;">ET Day: {et_day_str} | Reported: {html.escape(date_str)} | Period: {html.escape(str(period))}</div>
                <table border="0" cellpadding="6" cellspacing="0" style="margin-top:12px; background:#f8f9fb; border-radius:8px;">
                  <tr><td>EPS est</td><td>{fmt_num(eps_est)}</td><td>EPS actual</td><td>{fmt_num(eps_act)}</td></tr>
                  <tr><td>Revenue est</td><td>{fmt_num(rev_est)}</td><td>Revenue actual</td><td>{fmt_num(rev_act)}</td></tr>
                </table>

                <h3 style="margin-top:16px;">Key takeaways</h3>
                {summary_html}

                <h3 style="margin-top:16px;">Guidance / Forecast</h3>
                {guidance_html}

                <h3 style="margin-top:16px;">Same-day headlines</h3>
                <ul>{news_items_html}</ul>

                <div style="margin-top:16px; color:#777; font-size:12px;">
                  Automated note: Guidance is extracted from accessible press releases/news using heuristics and AI; verify with official filings/IR.
                </div>
              </body>
            </html>
            """

            subject = f"{t} — Quarterly results ({period})"
            try:
                send_email(smtp_host, smtp_port, smtp_user, smtp_pass, email_to, subject, html_body)
                print(f"[OK] sent: {t} {period}")
                sent_any = True
            except Exception as e:
                print(f"[ERROR] email failed for {t}: {e}")

    if not sent_any:
        print(f"[INFO] No earnings found for ET day {et_day_str} across {len(tickers)} tickers.")

if __name__ == "__main__":
    main()
