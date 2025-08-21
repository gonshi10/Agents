#!/usr/bin/env python3
"""
Smart Earnings Agent - Intelligent Stock Earnings Monitor with AI Insights
- Automatically fetches earnings data for stocks in watchlist.csv
- Uses AI to generate comprehensive summaries and insights
- Sends detailed email reports for each earnings announcement
- Simple rate limiting with delays between API calls
- Built-in error handling and reliability
"""

import csv
import os
import requests
import smtplib
import time
import random
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()

class EarningsAgent:
    def __init__(self):
        # Load environment variables
        self.finnhub_key = os.getenv('FINNHUB_API_KEY')
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_pass = os.getenv('SMTP_PASS')
        self.email_to = os.getenv('EMAIL_TO')
        self.model = os.getenv('OPENAI_MODEL')
        
        # Initialize OpenAI client
        if self.openai_key:
            self.openai_client = OpenAI(api_key=self.openai_key)
            print("✅ OpenAI SDK client initialized")
        else:
            self.openai_client = None
            print("⚠️ OpenAI API key not set - AI insights will be disabled")
        
        # Simple delay between Finnhub API calls (60 calls/minute = 1 call per second)
        self.finnhub_delay = 2.0  # 2 seconds between calls to stay well under limit
        
        # Rate limiting: wait a minute after 50 calls
        self.finnhub_call_count = 0
        self.last_reset_time = time.time()
        self.max_calls_before_wait = 50
        
        # OpenAI rate limiting
        self.openai_calls_per_minute = 3
        self.openai_call_times = []
        
        # Token management to stay within TPM limits
        self.max_tokens_per_request = 150  # Reduced from 300 for shorter insights
        self.max_input_tokens = 1500  # Reduced from 2000 for more focused input
        
        # Caching to avoid duplicate API calls
        self.insights_cache = {}
        
        # Validate required config
        if not all([self.finnhub_key, self.smtp_user, self.smtp_pass, self.email_to]):
            raise ValueError("Missing required environment variables. Check FINNHUB_API_KEY, SMTP_USER, SMTP_PASS, EMAIL_TO")
        
        print("✓ Configuration loaded successfully")
        print(f"📊 Finnhub rate limiting: {self.max_calls_before_wait} calls per minute with automatic waits")
    
    def check_rate_limit(self):
        """Check if we need to wait due to rate limiting"""
        current_time = time.time()
        
        # Reset counter if a minute has passed
        if current_time - self.last_reset_time >= 60:
            self.finnhub_call_count = 0
            self.last_reset_time = current_time
        
        # If we've made 50 calls, wait until the minute is up
        if self.finnhub_call_count >= self.max_calls_before_wait:
            wait_time = 60 - (current_time - self.last_reset_time) + 1  # Add 1 second buffer
            print(f"⏳ Rate limit reached (50 calls). Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            self.finnhub_call_count = 0
            self.last_reset_time = time.time()
            print("✅ Rate limit reset, continuing...")
        
        # Increment call counter
        self.finnhub_call_count += 1
    
    def wait_for_openai_rate_limit(self):
        """Simple OpenAI rate limiting"""
        now = time.time()
        
        # Remove calls older than 1 minute
        self.openai_call_times = [t for t in self.openai_call_times if now - t < 60]
        
        # If we've made too many calls recently, wait
        if len(self.openai_call_times) >= self.openai_calls_per_minute:
            wait_time = 60 - (now - self.openai_call_times[0]) + 2
            print(f"⏳ OpenAI rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            now = time.time()
        
        self.openai_call_times.append(now)
    
    def load_tickers(self, csv_file='watchlist.csv'):
        """Load ticker symbols from CSV"""
        tickers = []
        try:
            with open(csv_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get('Symbol', '').strip().upper()
                    if symbol:
                        tickers.append(symbol)
            
            print(f"✓ Loaded {len(tickers)} tickers: {', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''}")
            return tickers
        except Exception as e:
            print(f"✗ Failed to load tickers: {e}")
            return []
    
    def get_earnings_data(self, ticker, date_str):
        """Get earnings data for a ticker on a specific date"""
        try:
            # Check rate limit before making API call
            self.check_rate_limit()
            
            url = "https://finnhub.io/api/v1/calendar/earnings"
            params = {
                'token': self.finnhub_key,
                'from': date_str,
                'to': date_str,
                'symbol': ticker
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            earnings = data.get('earningsCalendar', [])
            
            if earnings:
                print(f"✓ Found {len(earnings)} earnings events for {ticker}")
                return earnings[0]  # Return first earnings event
            else:
                print(f"ℹ No earnings found for {ticker} on {date_str}")
                return None
                
        except Exception as e:
            print(f"✗ Failed to get earnings for {ticker}: {e}")
            return None
    
    def get_company_news(self, ticker, date_str):
        """Get company news for a ticker on a specific date"""
        try:
            # Check rate limit before making API call
            self.check_rate_limit()
            
            url = "https://finnhub.io/api/v1/company-news"
            params = {
                'token': self.finnhub_key,
                'symbol': ticker,
                'from': date_str,
                'to': date_str
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            news = data or []
            
            # Enhanced filtering for earnings-related news and guidance
            relevant_news = []
            for item in news:
                headline = item.get('headline', '').lower()
                # Look for guidance, outlook, forecasts, and strategic announcements
                if any(keyword in headline for keyword in [
                    'earnings', 'quarterly', 'results', 'guidance', 'outlook', 'forecast', 
                    'investor', 'conference', 'call', 'press release', 'strategic', 'initiative',
                    'expansion', 'acquisition', 'partnership', 'restructuring', 'cost cutting'
                ]):
                    relevant_news.append(item)
            
            print(f"✓ Found {len(relevant_news)} relevant news items for {ticker}")
            return relevant_news[:5]  # Increased to 5 to capture more guidance context
            
        except Exception as e:
            print(f"✗ Failed to get news for {ticker}: {e}")
            return []
    
    def optimize_context_for_tokens(self, tickers_data):
        """Optimize context to stay within token limits with enhanced guidance analysis"""
        def format_number(value):
            if value is None or value == 'N/A':
                return 'N/A'
            try:
                return f"{float(value):.2f}"
            except (ValueError, TypeError):
                return str(value)
        
        optimized_context = """Analyze earnings results and provide sophisticated, forward-looking insights for each company. Focus on:

1. GUIDANCE ANALYSIS: Extract and analyze forward-looking statements, outlook, and strategic initiatives
2. STRATEGIC IMPLICATIONS: What the numbers mean for future growth, market position, and competitive advantage
3. RISK FACTORS: Identify potential challenges and how management is addressing them
4. INVESTMENT THESIS: Why investors should care beyond the obvious beats/misses

Avoid stating the obvious (e.g., "EPS increased"). Instead, focus on strategic insights and guidance implications.

Format: TICKER: [3-4 sophisticated insights with guidance analysis]

"""
        
        for ticker, data in tickers_data.items():
            earnings = data['earnings']
            news = data['news']
            
            # Extract guidance insights
            guidance_insights = self.extract_guidance_insights(news)
            
            # Create comprehensive context with guidance focus
            context_line = f"""{ticker}: 
EPS: {format_number(earnings.get('epsEstimate'))}→{format_number(earnings.get('epsActual'))} 
Revenue: {format_number(earnings.get('revenueEstimate'))}→{format_number(earnings.get('revenueActual'))}
Guidance & Strategic Context: {' | '.join(guidance_insights) if guidance_insights else 'Limited guidance available'}

"""
            optimized_context += context_line
        
        return optimized_context
    
    def generate_ai_insights_single(self, ticker, earnings_data, news_data):
        """Generate AI insights for a single ticker using OpenAI SDK with enhanced guidance analysis"""
        if not self.openai_client:
            return "AI insights disabled - set OPENAI_API_KEY to enable"
        
        # Check cache first
        cache_key = f"{ticker}_{earnings_data.get('epsActual', 'N/A')}"
        if cache_key in self.insights_cache:
            print(f"✓ Using cached insights for {ticker}")
            return self.insights_cache[cache_key]
        
        try:
            # Wait for rate limiting
            self.wait_for_openai_rate_limit()
            
            # Format numbers for better readability
            def format_number(value):
                if value is None or value == 'N/A':
                    return 'N/A'
                try:
                    return f"{float(value):.2f}"
                except (ValueError, TypeError):
                    return str(value)
            
            # Build optimized context for single ticker
            context = f"""
Analyze {ticker} earnings:

EPS: Est {format_number(earnings_data.get('epsEstimate'))} vs Actual {format_number(earnings_data.get('epsActual'))}
Revenue: Est {format_number(earnings_data.get('revenueEstimate'))} vs Actual {format_number(earnings_data.get('revenueActual'))}

Key news: {', '.join([item.get('headline', 'N/A')[:40] for item in news_data[:1]])}

Provide 2 concise, actionable insights. Focus on:
- Strategic implications
- Forward-looking guidance
- Key risks or opportunities

Keep each insight under 15 words.
"""
            
            print(f"🤖 Generating focused AI insights for {ticker}...")
            
            # Use OpenAI SDK with enhanced prompt
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst. Provide 2 concise, actionable insights per company. Each insight must be under 15 words. Focus on strategic implications, guidance, and key risks/opportunities. Use bullet points."},
                    {"role": "user", "content": context}
                ],
                max_tokens=self.max_tokens_per_request
            )
            
            content = response.choices[0].message.content
            
            # Cache the result
            self.insights_cache[cache_key] = content
            
            print(f"✓ Generated enhanced AI insights for {ticker}")
            return content
            
        except Exception as e:
            print(f"✗ AI insights failed for {ticker}: {e}")
            return f"AI insights unavailable: {str(e)}"
    
    def generate_batched_ai_insights(self, tickers_data):
        """Generate AI insights for multiple tickers in one API call using OpenAI SDK"""
        if not self.openai_client:
            return {ticker: "AI insights disabled - set OPENAI_API_KEY to enable" for ticker in tickers_data.keys()}
        
        try:
            # Wait for rate limiting
            self.wait_for_openai_rate_limit()
            
            # Optimize context to stay within token limits
            context = self.optimize_context_for_tokens(tickers_data)
            
            print(f"🤖 Generating batched AI insights for {len(tickers_data)} tickers...")
            
            # Use OpenAI SDK for batch processing
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst. For each company, provide 2 concise, actionable insights. Each insight must be under 15 words. Focus on strategic implications, guidance, and key risks/opportunities. Use bullet points and format as 'TICKER: • Insight 1 • Insight 2'"},
                    {"role": "user", "content": context}
                ],
                max_tokens=self.max_tokens_per_request * len(tickers_data)  # Scale tokens with ticker count
            )
            
            content = response.choices[0].message.content
            
            # Debug: Show the raw AI response
            print(f"✓ Generated AI insights for {len(tickers_data)} tickers in one API call")
            
            # Parse the response to extract insights for each ticker
            insights = {}
            current_ticker = None
            current_insights = []
            
            # More robust parsing - try multiple approaches
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line starts with a ticker symbol
                ticker_found = None
                for ticker in tickers_data.keys():
                    if line.upper().startswith(ticker.upper()):
                        ticker_found = ticker
                        break
                
                if ticker_found:
                    # Save previous ticker's insights
                    if current_ticker:
                        insights[current_ticker] = '\n'.join(current_insights) if current_insights else "No insights available"
                    
                    # Start new ticker
                    current_ticker = ticker_found
                    current_insights = []
                elif current_ticker and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                    current_insights.append(line)
                elif current_ticker and line:
                    # If line doesn't start with bullet but has content, treat as insight
                    current_insights.append(f"• {line}")
            
            # Save last ticker's insights
            if current_ticker:
                insights[current_ticker] = '\n'.join(current_insights) if current_insights else "No insights available"
            
            # Fill in any missing tickers
            for ticker in tickers_data.keys():
                if ticker not in insights:
                    insights[ticker] = "AI insights unavailable"
            
            return insights
            
        except Exception as e:
            print(f"✗ Batched AI insights failed: {e}")
            print("⏳ Falling back to individual API calls...")
            return self.generate_individual_insights(tickers_data)
    
    def generate_individual_insights(self, tickers_data):
        """Generate AI insights for each ticker individually - fallback method"""
        print("🔄 Generating insights individually to avoid rate limiting...")
        
        insights = {}
        for i, (ticker, data) in enumerate(tickers_data.items()):
            print(f" Processing {ticker} ({i+1}/{len(tickers_data)})...")
            
            insight = self.generate_ai_insights_single(ticker, data['earnings'], data['news'])
            insights[ticker] = insight
            
            # Wait between individual calls to avoid rate limiting
            if i < len(tickers_data) - 1:
                wait_time = random.uniform(10, 15)
                print(f"⏳ Waiting {wait_time:.1f}s before next ticker...")
                time.sleep(wait_time)
        
        return insights
    
    def extract_guidance_insights(self, news_data):
        """Extract guidance and strategic insights from news data"""
        guidance_insights = []
        
        for item in news_data:
            headline = item.get('headline', '').lower()
            summary = item.get('summary', '')
            
            # Look for guidance-related content
            if any(keyword in headline for keyword in ['guidance', 'outlook', 'forecast', 'expects', 'targets']):
                guidance_insights.append(f"GUIDANCE: {item.get('headline', 'N/A')}")
            elif any(keyword in headline for keyword in ['strategic', 'initiative', 'expansion', 'acquisition']):
                guidance_insights.append(f"STRATEGIC: {item.get('headline', 'N/A')}")
            elif any(keyword in headline for keyword in ['restructuring', 'cost cutting', 'efficiency']):
                guidance_insights.append(f"OPERATIONAL: {item.get('headline', 'N/A')}")
            elif any(keyword in headline for keyword in ['investor', 'conference', 'call', 'press release']):
                guidance_insights.append(f"INVESTOR RELATIONS: {item.get('headline', 'N/A')}")
        
        return guidance_insights[:3]  # Return top 3 most relevant
    
    def create_email_content(self, ticker, earnings_data, news_data, ai_insights):
        """Create simple, clean email content"""
        # Format numbers as floats with 2 decimal places
        def format_number(value):
            if value is None or value == 'N/A':
                return 'N/A'
            try:
                return f"{float(value):.2f}"
            except (ValueError, TypeError):
                return str(value)
        
        eps_est = format_number(earnings_data.get('epsEstimate'))
        eps_act = format_number(earnings_data.get('epsActual'))
        
        # Handle revenue conversion properly
        try:
            rev_est_raw = earnings_data.get('revenueEstimate')
            rev_act_raw = earnings_data.get('revenueActual')
            
            if rev_est_raw and rev_est_raw != 'N/A':
                rev_est_val = float(rev_est_raw)
                if rev_est_val >= 1_000_000_000:
                    rev_est = f"{format_number(rev_est_val / 1_000_000_000)}B"
                else:
                    rev_est = f"{format_number(rev_est_val / 1_000_000)}M"
            else:
                rev_est = 'N/A'
                
            if rev_act_raw and rev_act_raw != 'N/A':
                rev_act_val = float(rev_act_raw)
                if rev_act_val >= 1_000_000_000:
                    rev_act = f"{format_number(rev_act_val / 1_000_000_000)}B"
                else:
                    rev_act = f"{format_number(rev_act_val / 1_000_000)}M"
            else:
                rev_act = 'N/A'
        except (ValueError, TypeError):
            rev_est = rev_act = 'N/A'
        
        # Calculate beats/misses
        try:
            # Check if we have valid data for comparison
            eps_est_valid = earnings_data.get('epsEstimate') and earnings_data.get('epsEstimate') != 'N/A'
            eps_act_valid = earnings_data.get('epsActual') and earnings_data.get('epsActual') != 'N/A'
            rev_est_valid = earnings_data.get('revenueEstimate') and earnings_data.get('revenueEstimate') != 'N/A'
            rev_act_valid = earnings_data.get('revenueActual') and earnings_data.get('revenueActual') != 'N/A'
            
            if eps_est_valid and eps_act_valid:
                eps_beat = "✓ BEAT" if float(earnings_data.get('epsActual')) > float(earnings_data.get('epsEstimate')) else "✗ MISS"
            else:
                eps_beat = "—"
                
            if rev_est_valid and rev_act_valid:
                rev_beat = "✓ BEAT" if float(earnings_data.get('revenueActual')) > float(earnings_data.get('revenueEstimate')) else "✗ MISS"
            else:
                rev_beat = "—"
             
        except (ValueError, TypeError) as e:
            eps_beat = rev_beat = "—"
        
        # Pre-format the insights for HTML
        formatted_insights = self.format_insights_for_html(ai_insights)
        
        # Simple, clean HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    min-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                    box-sizing: border-box;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 25px;
                    border-radius: 12px;
                    text-align: center;
                    margin-bottom: 25px;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 2em;
                    font-weight: 300;
                }}
                .card {{
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    width: 100%;
                    box-sizing: border-box;
                    overflow: visible;
                }}
                /* New styles for dashboard grid */
                .dashboard-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-top: 20px;
                }}
                .metric-card {{
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 8px;
                    padding: 20px;
                    text-align: center;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                .metric-header {{
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-bottom: 15px;
                    color: #495057;
                }}
                .metric-icon {{
                    font-size: 2em;
                    margin-right: 10px;
                }}
                .metric-title {{
                    font-size: 1.1em;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                .metric-values {{
                    margin-bottom: 15px;
                }}
                .actual-value {{
                    font-size: 2.5em;
                    font-weight: bold;
                    color: #2c3e50;
                }}
                .estimate-value {{
                    font-size: 0.9em;
                    color: #6c757d;
                    margin-top: 5px;
                }}
                .progress-container {{
                    margin-top: 15px;
                }}
                .progress-bar {{
                    height: 10px;
                    background-color: #e9ecef;
                    border-radius: 5px;
                    overflow: hidden;
                    margin-bottom: 8px;
                }}
                .progress-fill {{
                    height: 100%;
                    border-radius: 5px;
                    background: linear-gradient(to right, #28a745, #6c757d, #dc3545);
                    transition: width 0.3s ease-in-out;
                }}
                .progress-fill.beat {{
                    background: linear-gradient(to right, #28a745, #20c997);
                }}
                .progress-fill.miss {{
                    background: linear-gradient(to right, #dc3545, #fd7e14);
                }}
                .progress-fill.neutral {{
                    background: linear-gradient(to right, #6c757d, #495057);
                }}
                .progress-label {{
                    font-size: 0.9em;
                    font-weight: 600;
                    padding: 6px 12px;
                    border-radius: 20px;
                    display: inline-block;
                    min-width: 80px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-top: 10px;
                    margin-bottom: 10px;
                }}
                .progress-label.beat {{
                    background: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                }}
                .progress-label.miss {{
                    background: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                }}
                .progress-label.neutral {{
                    background: #e2e3e5;
                    color: #383d41;
                    border: 1px solid #d6d8db;
                }}
                .insights {{
                    background: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 20px;
                    border-radius: 4px;
                    line-height: 1.6;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                    white-space: normal;
                    max-width: 100%;
                    box-sizing: border-box;
                    min-height: 60px;
                    display: block;
                    overflow: visible;
                    text-overflow: clip;
                }}
                .insights p {{
                    margin: 0 0 15px 0;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                }}
                .insights p:last-child {{
                    margin-bottom: 0;
                }}
                .insight-item {{
                    display: flex;
                    align-items: flex-start;
                    margin-bottom: 15px;
                    padding: 12px 15px;
                    background: rgba(255, 255, 255, 0.7);
                    border-radius: 6px;
                    border-left: 3px solid #ffc107;
                    transition: all 0.2s ease;
                }}
                .insight-item:hover {{
                    background: rgba(255, 255, 255, 0.9);
                    transform: translateX(2px);
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
                .insight-bullet {{
                    font-size: 1.3em;
                    color: #ffc107;
                    margin-right: 12px;
                    font-weight: bold;
                    min-width: 20px;
                }}
                .insight-number {{
                    font-size: 1.3em;
                    color: #ffc107;
                    margin-right: 12px;
                    font-weight: bold;
                    min-width: 20px;
                }}
                .insight-text {{
                    flex-grow: 1;
                    font-size: 0.95em;
                    color: #343a40;
                    line-height: 1.5;
                    font-weight: 500;
                }}
                .insights-container {{
                    margin-top: 20px;
                    padding-top: 15px;
                    border-top: 1px solid #eee;
                }}
                .insights-header {{
                    font-size: 1.2em;
                    font-weight: 700;
                    color: #495057;
                    margin-bottom: 20px;
                    padding: 10px 15px;
                    border-bottom: 2px solid #ffc107;
                    padding-bottom: 10px;
                    background: rgba(255, 193, 7, 0.1);
                    border-radius: 6px 6px 0 0;
                }}
                .no-insights {{
                    font-style: italic;
                    color: #6c757d;
                    padding: 15px;
                    text-align: center;
                }}
                .news-item {{
                    padding: 10px 0;
                    border-bottom: 1px solid #eee;
                }}
                .news-item:last-child {{
                    border-bottom: none;
                }}
                .news-item a {{
                    color: #007bff;
                    text-decoration: none;
                }}
                .news-item a:hover {{
                    text-decoration: underline;
                }}
                .footer {{
                    text-align: center;
                    color: #6c757d;
                    font-size: 0.9em;
                    margin-top: 30px;
                }}
                .performance-status {{
                    font-size: 1em;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 20px;
                    display: inline-block;
                    min-width: 100px;
                    text-align: center;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-top: 10px;
                    margin-bottom: 10px;
                }}
                .performance-status.beat {{
                    background: #d4edda;
                    color: #155724;
                    border: 2px solid #c3e6cb;
                }}
                .performance-status.miss {{
                    background: #f8d7da;
                    color: #721c24;
                    border: 2px solid #f5c6cb;
                }}
                .performance-status.neutral {{
                    background: #e2e3e5;
                    color: #383d41;
                    border: 2px solid #d6d8db;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{ticker}</h1>
                <p>Earnings Report</p>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">📊 Financial Results</h3>
                
                <div class="dashboard-grid">
                    <!-- EPS Section -->
                    <div class="metric-card eps-card">
                        <div class="metric-header">
                            <span class="metric-icon">📈</span>
                            <span class="metric-title">Earnings Per Share</span>
                        </div>
                        <div class="metric-values">
                            <div class="actual-value">{eps_act}</div>
                            <div class="estimate-value">Est: {eps_est}</div>
                            <div class="performance-status {'beat' if 'BEAT' in eps_beat else 'miss' if 'MISS' in eps_beat else 'neutral'}">
                                {eps_beat.replace('✓ ', '').replace('✗ ', '') if eps_beat != '—' else '—'}
                            </div>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar">
                                <div class="progress-fill {'beat' if 'BEAT' in eps_beat else 'miss' if 'MISS' in eps_beat else 'neutral'}" style="width: {'85%' if 'BEAT' in eps_beat else '65%' if 'MISS' in eps_beat else '50%'}"></div>
                            </div>
                        </div>
                    </div>

                    <!-- Revenue Section -->
                    <div class="metric-card revenue-card">
                        <div class="metric-header">
                            <span class="metric-icon">💰</span>
                            <span class="metric-title">Revenue</span>
                        </div>
                        <div class="metric-values">
                            <div class="actual-value">{rev_act}</div>
                            <div class="estimate-value">Est: {rev_est}</div>
                            <div class="performance-status {'beat' if 'BEAT' in rev_beat else 'miss' if 'MISS' in rev_beat else 'neutral'}">
                                {rev_beat.replace('✓ ', '').replace('✗ ', '') if rev_beat != '—' else '—'}
                            </div>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar">
                                <div class="progress-fill {'beat' if 'BEAT' in rev_beat else 'miss' if 'MISS' in rev_beat else 'neutral'}"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">🧠 AI Insights</h3>
                <div class="insights">
                    {formatted_insights}
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">📰 Recent News</h3>
                {chr(10).join([f'<div class="news-item"><a href="{item.get("url", "#")}" target="_blank">{item.get("headline", "N/A")}</a></div>' for item in news_data[:3]])}
            </div>
            
            <div class="footer">
                Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                Powered by OpenAI GPT-3.5 Turbo
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def send_email(self, ticker, subject, html_content, earnings_data, news_data, ai_insights):
        """Send email"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_user
            msg['To'] = self.email_to
            msg['Subject'] = subject
            
            # Format revenue numbers for plain text
            def format_revenue(value):
                if value is None or value == 'N/A':
                    return 'N/A'
                try:
                    val = float(value)
                    if val >= 1_000_000_000:
                        return f"{val / 1_000_000_000:.2f}B"
                    else:
                        return f"{val / 1_000_000:.2f}M"
                except (ValueError, TypeError):
                    return str(value)
            
            rev_est = format_revenue(earnings_data.get('revenueEstimate'))
            rev_act = format_revenue(earnings_data.get('revenueActual'))
            
            # Create simple plain text version
            text_content = f"""
 {ticker} EARNINGS REPORT
 {'=' * (len(ticker) + 16)}
 
 📊 FINANCIAL RESULTS
 {'-' * 20}
 
 EPS: {earnings_data.get('epsEstimate', 'N/A')} → {earnings_data.get('epsActual', 'N/A')}
 Revenue: {rev_est} → {rev_act}
 
 🧠 AI INSIGHTS
 {'-' * 15}
 {ai_insights.replace('<br>', '\n').replace('<strong>', '').replace('</strong>', '').replace('•', '• ')}
 
 📰 RECENT NEWS
 {'-' * 15}
 {chr(10).join([f'• {item.get("headline", "N/A")}' for item in news_data[:3]])}
 
 {'=' * 40}
 Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
 Powered by OpenAI GPT-3.5 Turbo
 {'=' * 40}
 """
            
            # Remove HTML tags
            import re
            text_content = re.sub(r'<[^>]+>', '', text_content)
            
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Send email
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            print(f"✓ Email sent successfully")
            return True
            
        except Exception as e:
            print(f"✗ Failed to send email: {e}")
            return False
    
    def run(self, test_mode=False):
        """Main execution with simple rate limiting"""
        print("🚀 Starting Smart Earnings Agent with Simple Rate Limiting...")
        
        # Determine date to check
        if test_mode:
            target_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        else:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"📅 Checking earnings for: {target_date}")
        
        # Load tickers
        tickers = self.load_tickers()
        if not tickers:
            print("❌ No tickers loaded. Exiting.")
            return
        
        print(f"📊 Processing {len(tickers)} tickers with simple delays...")
        
        # Collect all data with simple delays between API calls
        print("\n📊 Collecting earnings data and news...")
        tickers_data = {}
        
        for i, ticker in enumerate(tickers, 1):
            print(f"\n--- Processing {ticker} ({i}/{len(tickers)}) ---")
            
            # Get earnings data
            earnings = self.get_earnings_data(ticker, target_date)
            if not earnings:
                print(f"ℹ No earnings found for {ticker}, skipping...")
                continue
            
            # Get news
            news = self.get_company_news(ticker, target_date)
            
            # Store data
            tickers_data[ticker] = {
                'earnings': earnings,
                'news': news
            }
            
            # Progress update
            if i % 10 == 0:
                print(f"📈 Progress: {i}/{len(tickers)} tickers processed ({i/len(tickers)*100:.1f}%)")
        
        if not tickers_data:
            print("❌ No earnings data found. Exiting.")
            return
        
        print(f"\n✅ Successfully collected data for {len(tickers_data)} tickers")
        
        print(f"\n🤖 Generating AI insights for {len(tickers_data)} tickers...")
        
        # Generate AI insights
        ai_insights = self.generate_batched_ai_insights(tickers_data)
        
        print(f"\n📧 Sending emails...")
        
        # Send emails
        emails_sent = 0
        
        for ticker, data in tickers_data.items():
            print(f"\n--- Sending email for {ticker} ---")
            
            # Create and send email
            subject = f"{ticker} Earnings Report"
            html_content = self.create_email_content(ticker, data['earnings'], data['news'], ai_insights.get(ticker, 'No insights available'))
            
            if self.send_email(ticker, subject, html_content, data['earnings'], data['news'], ai_insights.get(ticker, 'No insights available')):
                emails_sent += 1
        
        print(f"\n🎉 Processing complete! Sent {emails_sent} emails for {target_date}")
        print("✅ Simple rate limiting implemented successfully")

    def format_insights_for_html(self, insights_text):
        """Format AI insights with proper HTML structure and titles"""
        if not insights_text or insights_text == "AI insights unavailable":
            return '<div class="no-insights">No AI insights available</div>'
        
        # Split insights into lines and clean them up
        lines = insights_text.strip().split('\n')
        formatted_insights = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if this is a bullet point or numbered item
            if line.startswith('•') or line.startswith('-') or line.startswith('*'):
                # Extract the insight text
                insight_text = line[1:].strip()
                if insight_text:
                    formatted_insights.append(f'<div class="insight-item"><span class="insight-bullet">•</span><span class="insight-text">{insight_text}</span></div>')
            elif line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or line.startswith('4.'):
                # Handle numbered insights
                parts = line.split('.', 1)
                if len(parts) > 1:
                    insight_text = parts[1].strip()
                    if insight_text:
                        formatted_insights.append(f'<div class="insight-item"><span class="insight-number">{parts[0]}.</span><span class="insight-text">{insight_text}</span></div>')
            elif line and not line.startswith('TICKER:'):
                # Treat as regular insight text
                formatted_insights.append(f'<div class="insight-item"><span class="insight-bullet">•</span><span class="insight-text">{line}</span></div>')
        
        if not formatted_insights:
            return '<div class="no-insights">No structured insights available</div>'
        
        # Create the formatted HTML
        html_content = '<div class="insights-container">'
        html_content += '<div class="insights-header">Key Strategic Insights</div>'
        html_content += ''.join(formatted_insights)
        html_content += '</div>'
        
        return html_content

def main():
    """Main entry point"""
    import sys

    try:
        agent = EarningsAgent()
        agent.run(test_mode=os.getenv('TEST_MODE') == 'true')
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()