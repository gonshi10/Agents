#!/usr/bin/env python3
"""
Earnings Watchlist Agent — Intelligent Stock Earnings Monitor
- Automatically fetches earnings data for stocks in watchlist.csv
- Uses AI to generate comprehensive summaries and insights
- Sends detailed email reports for each earnings announcement
- Extracts guidance and forward-looking statements
- Built-in rate limiting and error handling
"""

import csv
import html
import os
import re
import smtplib
import asyncio
import aiohttp
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple, Dict, Any
import json
from zoneinfo import ZoneInfo
import time
from config import Config

# Constants
FINNHUB_BASE = "https://finnhub.io/api/v1"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# HTML processing regex patterns (compiled once for efficiency)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
NEWLINE_RE = re.compile(r"\n{3,}")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", flags=re.DOTALL | re.IGNORECASE)
NAV_ASIDE_RE = re.compile(r"<(aside|nav|footer|header)[^>]*>.*?</\1>", flags=re.DOTALL | re.IGNORECASE)

class EarningsProcessor:
    """Main class for processing earnings data"""
    
    def __init__(self):
        self.config = Config()
        self.session = None
        self.earnings_cache = {}
        
    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return missing items"""
        missing = self.config.validate()
        if missing:
            print(f"[ERROR] Missing required configuration: {', '.join(missing)}")
        return missing
    
    def load_tickers(self) -> List[str]:
        """Load ticker symbols from CSV file"""
        try:
            tickers = []
            with open(self.config.WATCHLIST_CSV, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                    if sym:
                        tickers.append(sym)
            
            if not tickers:
                raise RuntimeError("No tickers found in CSV")
            
            tickers = sorted(set(tickers))  # Remove duplicates
            print(f"[INFO] Loaded {len(tickers)} tickers from {self.config.WATCHLIST_CSV}")
            return tickers
            
        except Exception as e:
            print(f"[ERROR] Failed to load tickers: {e}")
            raise
    
    async def fetch_earnings_data(self, ticker: str, date_str: str) -> List[Dict[str, Any]]:
        """Fetch earnings data for a specific ticker and date"""
        try:
            params = {
                "token": self.config.FINNHUB_API_KEY,
                "from": date_str,
                "to": date_str,
                "symbol": ticker
            }
            
            async with self.session.get(f"{FINNHUB_BASE}/calendar/earnings", params=params) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("earningsCalendar", []) or []
                
        except Exception as e:
            print(f"[WARN] Failed to fetch earnings for {ticker}: {e}")
            return []
    
    async def fetch_company_news(self, ticker: str, date_str: str) -> List[Dict[str, Any]]:
        """Fetch company news for a specific ticker and date"""
        try:
            params = {
                "token": self.config.FINNHUB_API_KEY,
                "symbol": ticker,
                "from": date_str,
                "to": date_str
            }
            
            async with self.session.get(f"{FINNHUB_BASE}/company-news", params=params) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Filter and prioritize relevant news
                relevant_news = []
                for news in data or []:
                    headline = (news.get("headline") or "").strip()
                    url = (news.get("url") or "").strip()
                    
                    # Check if news is earnings-related
                    is_earnings_related = any(keyword in headline.lower() for keyword in [
                        "earnings", "quarterly", "results", "guidance", "outlook", "forecast"
                    ])
                    
                    # Check if source is press release
                    is_press_release = any(domain in url.lower() for domain in [
                        "businesswire.com", "prnewswire.com", "globenewswire.com",
                        "newsfilecorp.com", "investor", "ir.", "/press-", "/pressrelease"
                    ])
                    
                    if is_earnings_related or is_press_release:
                        relevant_news.append(news)
                
                # Sort by datetime (newest first)
                relevant_news.sort(key=lambda x: x.get("datetime", 0), reverse=True)
                return relevant_news[:10]  # Limit to top 10
                
        except Exception as e:
            print(f"[WARN] Failed to fetch news for {ticker}: {e}")
            return []
    
    async def fetch_press_release_text(self, url: str) -> str:
        """Fetch and extract text from press release URL"""
        if not url:
            return ""
        
        try:
            # Skip problematic URLs that are likely to fail
            if any(skip_domain in url.lower() for skip_domain in [
                'wsj.com', 'bloomberg.com', 'reuters.com', 'cnbc.com', 'marketwatch.com'
            ]):
                print(f"[INFO] Skipping {url} - known to block scraping")
                return ""
            
            # Set reasonable headers to avoid header length issues
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            async with self.session.get(url, headers=headers, timeout=15) as response:
                if response.status == 403:
                    print(f"[INFO] Access forbidden for {url} - site blocks scraping")
                    return ""
                elif response.status == 429:
                    print(f"[INFO] Rate limited for {url} - too many requests")
                    return ""
                elif response.status >= 400:
                    print(f"[WARN] HTTP {response.status} for {url}")
                    return ""
                
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type:
                    print(f"[INFO] Non-HTML content for {url}: {content_type}")
                    return ""
                
                html_content = await response.text()
                return self.extract_main_text(html_content)
                
        except asyncio.TimeoutError:
            print(f"[WARN] Timeout fetching {url}")
            return ""
        except Exception as e:
            # Don't print the full error for header length issues
            if "Header value is too long" in str(e):
                print(f"[INFO] Header too long for {url} - skipping")
            elif "HTTP Forbidden" in str(e):
                print(f"[INFO] Access forbidden for {url}")
            else:
                print(f"[WARN] Failed to fetch press release from {url}: {e}")
            return ""
    
    def extract_main_text(self, html_text: str) -> str:
        """Extract main text content from HTML"""
        if not html_text:
            return ""
        
        # Try to find article containers
        blocks = []
        
        # Look for common article wrappers
        article_patterns = [
            r"<article[^>]*>.*?</article>",
            r"<div[^>]+class=[\"'][^\"']*(?:article|entry|post|content|story|pr|press)[^\"']*[\"'][^>]*>.*?</div>",
            r"<section[^>]+class=[\"'][^\"']*(?:content|story)[^\"']*[\"'][^>]*>.*?</section>",
        ]
        
        for pattern in article_patterns:
            matches = re.finditer(pattern, html_text, flags=re.DOTALL | re.IGNORECASE)
            for match in matches:
                blocks.append(html_text[match.start():match.end()])
        
        # Fallback to paragraph tags
        if not blocks:
            p_tags = re.findall(r"<p[^>]*>.*?</p>", html_text, flags=re.DOTALL | re.IGNORECASE)
            if p_tags:
                blocks = ["\n".join(p_tags)]
        
        if not blocks:
            return ""
        
        # Choose the largest text block
        best_block = max(blocks, key=len)
        
        # Clean up the content
        best_block = SCRIPT_STYLE_RE.sub("", best_block)
        best_block = NAV_ASIDE_RE.sub("", best_block)
        
        # Extract and clean text
        text = TAG_RE.sub("\n", best_block)
        text = WHITESPACE_RE.sub(" ", text)
        text = NEWLINE_RE.sub("\n\n", text)
        
        # Limit text length for AI processing
        if len(text) > self.config.MAX_PRESS_TEXT_LENGTH:
            text = text[:self.config.MAX_PRESS_TEXT_LENGTH] + "\n[...]"
        
        return text.strip()
    
    def extract_guidance(self, text: str) -> List[str]:
        """Extract guidance and forward-looking statements from text"""
        guidance_lines = []
        
        # Common guidance patterns
        patterns = [
            (r"revenue.*?guidance.*?\$?\s*([0-9][0-9,\.]*)\s*(?:to|-|–|—)\s*\$?\s*([0-9][0-9,\.]*)", "Revenue guidance: {}-{}"),
            (r"revenue.*?guidance.*?\$?\s*([0-9][0-9,\.]*)", "Revenue guidance: {}"),
            (r"EPS.*?guidance.*?\$?\s*(-?[0-9][0-9\.,]*)(?:\s*(?:to|-|–|—)\s*\$?\s*(-?[0-9][0-9\.,]*))?", "EPS guidance: {}"),
            (r"margin.*?guidance.*?([0-9]{1,3}\.?[0-9]?)\s*%", "Margin guidance: {}%"),
            (r"growth.*?guidance.*?([0-9]{1,3}\.?[0-9]?)\s*%", "Growth guidance: {}%"),
        ]
        
        for pattern, template in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if match.groups():
                    if len(match.groups()) == 2 and match.group(2):
                        guidance_lines.append(template.format(match.group(1), match.group(2)))
                    else:
                        guidance_lines.append(template.format(match.group(1)))
        
        # Add period mentions
        period_matches = re.finditer(r"\b(FY\s?20\d{2}|fiscal\s+(?:year|quarter|Q[1-4]))\b", text, re.IGNORECASE)
        for match in period_matches:
            period = match.group(1).strip()
            if period and not any(period in line for line in guidance_lines):
                guidance_lines.append(f"Guidance period: {period}")
        
        # Remove duplicates and limit
        seen = set()
        unique_guidance = []
        for line in guidance_lines:
            if line not in seen:
                unique_guidance.append(line)
                seen.add(line)
        
        return unique_guidance[:self.config.MAX_GUIDANCE_LINES]
    
    async def generate_ai_summary(self, ticker: str, earnings_data: Dict[str, Any], 
                                 guidance_lines: List[str], news: List[Dict[str, Any]], 
                                 press_texts: List[str]) -> str:
        """Generate AI summary using OpenAI"""
        if not self.config.OPENAI_API_KEY:
            return "<p style='color:#777'>(AI summary disabled — set OPENAI_API_KEY to enable.)</p>"
        
        # Add delay to prevent rate limiting
        await asyncio.sleep(1.0)
        
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                # Build context for AI
                context = self.build_ai_context(ticker, earnings_data, guidance_lines, news, press_texts)
                
                # Prepare OpenAI request
                headers = {
                    "Authorization": f"Bearer {self.config.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": self.config.OPENAI_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": """You are an expert equity research analyst. Create a concise, data-driven summary (5-8 bullet points) of quarterly earnings results. Focus on:
1) EPS and revenue performance vs estimates (beat/miss magnitude)
2) Year-over-year and sequential growth rates
3) Forward guidance and outlook changes
4) Margin trends and operational metrics
5) Key business drivers and risks
6) Capital allocation (buybacks, dividends, capex)
7) Segment performance highlights
8) Investment implications

Use specific numbers and percentages. Be concise and actionable."""
                        },
                        {
                            "role": "user",
                            "content": context
                        }
                    ],
                    "temperature": self.config.OPENAI_TEMPERATURE,
                    "max_tokens": 500
                }
                
                # Make API call
                async with self.session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as response:
                    if response.status == 429:
                        # Rate limited - wait and retry
                        delay = base_delay * (2 ** attempt)
                        print(f"[INFO] OpenAI rate limited for {ticker}, waiting {delay}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(delay)
                        continue
                    
                    response.raise_for_status()
                    data = await response.json()
                    
                    content = data["choices"][0]["message"]["content"]
                    if not content:
                        raise ValueError("Empty response from OpenAI")
                    
                    # Convert markdown bullets to HTML
                    bullet_lines = [line.strip("-• ").strip() for line in content.splitlines() if line.strip()]
                    summary_html = "<ul>" + "".join(f"<li>{html.escape(line)}</li>" for line in bullet_lines) + "</ul>"
                    
                    print(f"[INFO] Generated AI summary for {ticker} with {len(bullet_lines)} bullet points")
                    return summary_html
                    
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    # Rate limited - wait and retry
                    delay = base_delay * (2 ** attempt)
                    print(f"[INFO] OpenAI rate limited for {ticker}, waiting {delay}s before retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    print(f"[WARN] AI summary failed for {ticker}: {e}")
                    return f"<p style='color:#777'>(AI summary unavailable: {html.escape(str(e))})</p>"
        
        # If we get here, all retries failed
        print(f"[WARN] AI summary failed for {ticker} after {max_retries} attempts")
        return f"<p style='color:#777'>(AI summary unavailable after multiple retries)</p>"
    
    def build_ai_context(self, ticker: str, earnings_data: Dict[str, Any], 
                         guidance_lines: List[str], news: List[Dict[str, Any]], 
                         press_texts: List[str]) -> str:
        """Build context string for AI analysis"""
        lines = [
            f"Ticker: {ticker}",
            f"Period: {earnings_data.get('period', 'Unknown')}",
            f"Report Date: {earnings_data.get('date', 'Unknown')}"
        ]
        
        # Add financial metrics
        eps_est = earnings_data.get('epsEstimate')
        eps_act = earnings_data.get('epsActual')
        rev_est = earnings_data.get('revenueEstimate')
        rev_act = earnings_data.get('revenueActual')
        
        if eps_est is not None or eps_act is not None:
            lines.append(f"EPS: estimate={eps_est}, actual={eps_act}")
        if rev_est is not None or rev_act is not None:
            lines.append(f"Revenue: estimate={rev_est}, actual={rev_act}")
        
        # Add guidance
        if guidance_lines:
            lines.append("Guidance:")
            lines.extend(f"- {line}" for line in guidance_lines)
        
        # Add news headlines
        if news:
            lines.append("News Headlines:")
            for item in news[:5]:
                headline = item.get('headline', '').strip()
                source = item.get('source', '').strip()
                lines.append(f"- {headline} [{source}]")
        
        # Add press release excerpts
        if press_texts:
            lines.append("Press Release Excerpts:")
            for text in press_texts[:2]:
                excerpt = " ".join(text.split()[:100])  # First 100 words
                if len(excerpt) > 500:
                    excerpt = excerpt[:500] + " [...]"
                lines.append(f"- {excerpt}")
        
        return "\n".join(lines)
    
    def format_number(self, value) -> str:
        """Format number values for display"""
        if value in (None, "", "null"):
            return "—"
        try:
            return f"{float(value):,.2f}"
        except (ValueError, TypeError):
            return str(value)
    
    def create_email_html(self, ticker: str, earnings_data: Dict[str, Any], 
                          guidance_lines: List[str], news: List[Dict[str, Any]], 
                          ai_summary: str, date_str: str) -> str:
        """Create HTML email content"""
        period = earnings_data.get('period', 'Unknown')
        eps_est = earnings_data.get('epsEstimate')
        eps_act = earnings_data.get('epsActual')
        rev_est = earnings_data.get('revenueEstimate')
        rev_act = earnings_data.get('revenueActual')
        
        # Create news items HTML
        news_items_html = ""
        if news:
            news_items_html = "".join(
                f"<li><a href='{html.escape(item.get('url', ''))}'>{html.escape(item.get('headline', ''))}</a> "
                f"<em>({html.escape(item.get('source', 'Unknown'))})</em></li>"
                for item in news
            )
        else:
            news_items_html = "<li>No relevant news items found</li>"
        
        # Create guidance HTML
        if guidance_lines:
            guidance_html = "<ul>" + "".join(f"<li>{html.escape(line)}</li>" for line in guidance_lines) + "</ul>"
        else:
            guidance_html = "<p style='color:#777'>No explicit guidance found in the accessible text.</p>"
        
        return f"""
        <html>
          <body style="font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height:1.45; color:#111;">
            <h2 style="margin:0 0 4px 0">{html.escape(ticker)} — Quarterly Results Recap</h2>
            <div style="color:#555;">ET Day: {date_str} | Period: {html.escape(str(period))}</div>
            
            <table border="0" cellpadding="6" cellspacing="0" style="margin-top:12px; background:#f8f9fb; border-radius:8px;">
              <tr><td>EPS est</td><td>{self.format_number(eps_est)}</td><td>EPS actual</td><td>{self.format_number(eps_act)}</td></tr>
              <tr><td>Revenue est</td><td>{self.format_number(rev_est)}</td><td>Revenue actual</td><td>{self.format_number(rev_act)}</td></tr>
            </table>

            <h3 style="margin-top:16px;">Key Takeaways</h3>
            {ai_summary}

            <h3 style="margin-top:16px;">Guidance / Forecast</h3>
            {guidance_html}

            <h3 style="margin-top:16px;">Relevant News</h3>
            <ul>{news_items_html}</ul>

            <div style="margin-top:16px; color:#777; font-size:12px;">
              Automated analysis: Data extracted from earnings reports and press releases. Verify with official filings.
            </div>
          </body>
        </html>
        """
    
    async def send_email(self, subject: str, html_body: str) -> bool:
        """Send email using configured SMTP settings"""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config.SMTP_USER
            msg["To"] = self.config.EMAIL_TO
            msg["Subject"] = subject

            # Create plain text version
            text_body = re.sub(r"<[^>]+>", "", html_body)
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Send email
            with smtplib.SMTP(self.config.SMTP_HOST, self.config.SMTP_PORT) as server:
                server.starttls()
                server.login(self.config.SMTP_USER, self.config.SMTP_PASS)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to send email: {e}")
            return False
    
    async def process_ticker(self, ticker: str, date_str: str) -> bool:
        """Process a single ticker for earnings data"""
        print(f"[INFO] Processing {ticker}...")
        
        try:
            # Fetch earnings data
            earnings_list = await self.fetch_earnings_data(ticker, date_str)
            if not earnings_list:
                print(f"[INFO] No earnings found for {ticker} on {date_str}")
                return False
            
            # Process each earnings event
            for earnings in earnings_list:
                print(f"[INFO] Processing {ticker} {earnings.get('period', 'Unknown')}")
                
                # Fetch news and press releases
                news = await self.fetch_company_news(ticker, date_str)
                print(f"[INFO] Found {len(news)} relevant news items for {ticker}")
                
                # Fetch press release text
                press_texts = []
                for item in news[:3]:  # Limit to 3 to avoid too many requests
                    url = item.get('url', '').strip()
                    if url:
                        text = await self.fetch_press_release_text(url)
                        if text:
                            press_texts.append(text)
                
                # Extract guidance
                combined_text = "\n".join([
                    item.get('headline', '') + " " + (item.get('summary', '') or '')
                    for item in news
                ] + press_texts)
                
                guidance_lines = self.extract_guidance(combined_text)
                if guidance_lines:
                    print(f"[INFO] Extracted {len(guidance_lines)} guidance lines for {ticker}")
                
                # Generate AI summary
                ai_summary = await self.generate_ai_summary(
                    ticker, earnings, guidance_lines, news, press_texts
                )
                
                # Create and send email
                subject = f"{ticker} — Quarterly Results ({earnings.get('period', 'Unknown')})"
                html_body = self.create_email_html(
                    ticker, earnings, guidance_lines, news, ai_summary, date_str
                )
                
                if await self.send_email(subject, html_body):
                    print(f"[SUCCESS] Sent email for {ticker} {earnings.get('period', 'Unknown')}")
                    return True
                else:
                    print(f"[ERROR] Failed to send email for {ticker}")
                    return False
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to process {ticker}: {e}")
            return False
    
    async def run(self):
        """Main execution method"""
        # Validate configuration
        missing_config = self.validate_config()
        if missing_config:
            print(f"[ERROR] Configuration incomplete. Missing: {', '.join(missing_config)}")
            return
        
        # Print configuration summary
        self.config.print_summary()
        
        # Check if we should run (midnight ET check)
        now_et = datetime.now(ZoneInfo("America/New_York"))
        if now_et.hour != 0 and not self.config.TEST_MODE:
            print(f"[INFO] Not midnight ET (now_et={now_et}); exiting.")
            return
        
        # Determine target date
        if self.config.TEST_MODE:
            target_date = (now_et - timedelta(days=3)).date()
        else:
            target_date = (now_et - timedelta(days=1)).date()
        
        date_str = target_date.isoformat()
        print(f"[INFO] Processing earnings for ET day: {date_str}")
        
        # Load tickers
        try:
            tickers = self.load_tickers()
            
            # In test mode, limit to first 3 tickers to avoid overwhelming APIs
            if self.config.TEST_MODE and len(tickers) > 3:
                tickers = tickers[:3]
                print(f"[INFO] Test mode: limiting to first 3 tickers: {', '.join(tickers)}")
                
        except Exception as e:
            print(f"[ERROR] Failed to load tickers: {e}")
            return
        
        # Process tickers
        success_count = 0
        total_count = len(tickers)
        
        for i, ticker in enumerate(tickers, 1):
            print(f"[INFO] Processing {ticker} ({i}/{total_count})")
            
            try:
                if await self.process_ticker(ticker, date_str):
                    success_count += 1
            except Exception as e:
                print(f"[ERROR] Failed to process {ticker}: {e}")
                continue
            
            # Rate limiting between tickers - longer delay to prevent API overload
            if i < total_count:
                delay = self.config.API_DELAY_SECONDS * 2  # Double the delay
                print(f"[INFO] Waiting {delay}s before next ticker...")
                await asyncio.sleep(delay)
        
        # Summary
        if success_count > 0:
            print(f"[SUCCESS] Processed {total_count} tickers, sent {success_count} emails for {date_str}")
        else:
            print(f"[INFO] No earnings found for {date_str} across {total_count} tickers")

async def main():
    """Main entry point"""
    async with EarningsProcessor() as processor:
        await processor.run()

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
