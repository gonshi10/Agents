#!/usr/bin/env python3
"""
Smart Earnings Agent - Intelligent Stock Earnings Monitor with AI Insights
- Automatically fetches earnings data for stocks in watchlist.csv
- Uses AI to generate comprehensive summaries and insights
- Sends detailed email reports for each earnings announcement
- Smart API batching and rate limiting with OpenAI SDK
- Built-in error handling and reliability
"""

import csv
import os
import requests
import smtplib
import time
import random
import json
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any
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
        
        # Initialize OpenAI client
        if self.openai_key:
            self.openai_client = OpenAI(api_key=self.openai_key)
            print("✅ OpenAI SDK client initialized")
        else:
            self.openai_client = None
            print("⚠️ OpenAI API key not set - AI insights will be disabled")
        
        # Enhanced OpenAI rate limiting with best practices
        self.openai_calls_per_minute = 3  # Increased since using SDK
        self.last_openai_call = 0
        self.openai_call_times = []
        
        # Token management to stay within TPM limits
        self.max_tokens_per_request = 300  # Conservative token limit
        self.max_input_tokens = 2000  # Limit input size
        
        # Caching to avoid duplicate API calls
        self.insights_cache = {}
        
        # Validate required config
        if not all([self.finnhub_key, self.smtp_user, self.smtp_pass, self.email_to]):
            raise ValueError("Missing required environment variables. Check FINNHUB_API_KEY, SMTP_USER, SMTP_PASS, EMAIL_TO")
        
        print("✓ Configuration loaded successfully")
    
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
    
    def wait_for_openai_rate_limit(self):
        """Enhanced rate limiting with SDK best practices"""
        now = time.time()
        
        # Remove calls older than 1 minute
        self.openai_call_times = [t for t in self.openai_call_times if now - t < 60]
        
        # If we've made too many calls recently, wait
        if len(self.openai_call_times) >= self.openai_calls_per_minute:
            wait_time = 60 - (now - self.openai_call_times[0]) + random.uniform(2, 5)
            print(f"⏳ OpenAI rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            now = time.time()
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(1.0, 3.0)
        time.sleep(jitter)
        
        self.openai_call_times.append(now)
        self.last_openai_call = now
    
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
Period: {earnings.get('period', 'Unknown')}
Guidance & Strategic Context: {' | '.join(guidance_insights) if guidance_insights else 'Limited guidance available'}

"""
            optimized_context += context_line
        
        return optimized_context
    
    def generate_ai_insights_single(self, ticker, earnings_data, news_data):
        """Generate AI insights for a single ticker using OpenAI SDK with enhanced guidance analysis"""
        if not self.openai_client:
            return "AI insights disabled - set OPENAI_API_KEY to enable"
        
        # Check cache first
        cache_key = f"{ticker}_{earnings_data.get('period', 'Unknown')}_{earnings_data.get('epsActual', 'N/A')}"
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
            
            # Enhanced context with guidance focus
            context = f"""Analyze {ticker} earnings results with sophisticated insights:

FINANCIAL RESULTS:
- Period: {earnings_data.get('period', 'Unknown')}
- EPS: Est {format_number(earnings_data.get('epsEstimate'))} vs Actual {format_number(earnings_data.get('epsActual'))}
- Revenue: Est {format_number(earnings_data.get('revenueEstimate'))} vs Actual {format_number(earnings_data.get('revenueActual'))}

GUIDANCE & STRATEGIC CONTEXT:
{chr(10).join([f"- {item.get('headline', 'N/A')}" for item in news_data[:3]])}

REQUIRED INSIGHTS (3-4 bullet points):
1. GUIDANCE ANALYSIS: Extract forward-looking statements and strategic initiatives
2. STRATEGIC IMPLICATIONS: What the results mean for future growth and market position
3. RISK ASSESSMENT: Identify challenges and management's response
4. INVESTMENT THESIS: Why this matters beyond obvious beats/misses

AVOID: Stating the obvious (e.g., "EPS increased"). Focus on strategic insights and guidance implications.
"""
            
            print(f"🤖 Generating enhanced AI insights for {ticker}...")
            
            # Use OpenAI SDK with enhanced prompt
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst specializing in earnings analysis and strategic insights. You excel at identifying forward-looking guidance, strategic implications, and investment theses. Avoid obvious statements and focus on sophisticated analysis."},
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
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst specializing in earnings analysis and strategic insights. You excel at identifying forward-looking guidance, strategic implications, and investment theses. For each company, provide 3-4 sophisticated insights that focus on guidance analysis, strategic implications, risk factors, and investment thesis. Avoid obvious statements and focus on sophisticated analysis."},
                    {"role": "user", "content": context}
                ],
                max_tokens=self.max_tokens_per_request * len(tickers_data)  # Scale tokens with ticker count
            )
            
            content = response.choices[0].message.content
            
            print(f"✓ Generated AI insights for {len(tickers_data)} tickers in one API call")
            
            # Debug: Show the raw AI response
            print(f"🔍 Raw AI response: {content}")
            print(f"🔍 Response length: {len(content)} characters")
            
            # Parse the response to extract insights for each ticker
            insights = {}
            current_ticker = None
            current_insights = []
            
            # More robust parsing - try multiple approaches
            lines = content.split('\n')
            print(f"🔍 Parsing {len(lines)} lines from AI response")
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                print(f"🔍 Line {i+1}: '{line}'")
                
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
                        print(f"✅ Saved insights for {current_ticker}: {len(current_insights)} items")
                    
                    # Start new ticker
                    current_ticker = ticker_found
                    current_insights = []
                    print(f"🔄 Starting new ticker: {current_ticker}")
                elif current_ticker and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                    current_insights.append(line)
                    print(f"📝 Added insight: {line}")
                elif current_ticker and line:
                    # If line doesn't start with bullet but has content, treat as insight
                    current_insights.append(f"• {line}")
                    print(f"📝 Added insight (with bullet): • {line}")
            
            # Save last ticker's insights
            if current_ticker:
                insights[current_ticker] = '\n'.join(current_insights) if current_insights else "No insights available"
                print(f"✅ Saved insights for {current_ticker}: {len(current_insights)} items")
            
            # Fill in any missing tickers
            for ticker in tickers_data.keys():
                if ticker not in insights:
                    insights[ticker] = "AI insights unavailable"
                    print(f"⚠️ No insights found for {ticker}, setting to unavailable")
            
            print(f"🔍 Final insights: {insights}")
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
        """Create email content"""
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
        rev_est = format_number(earnings_data.get('revenueEstimate'))
        rev_act = format_number(earnings_data.get('revenueActual'))
        period = earnings_data.get('period', 'Unknown')
        
        # Calculate beats/misses
        try:
            eps_beat = "✓ Beat" if eps_act and eps_est and float(eps_act) > float(eps_est) else "✗ Miss" if eps_act and eps_est and float(eps_act) < float(eps_est) else "—"
            rev_beat = "✓ Beat" if rev_act and rev_est and float(rev_act) > float(rev_est) else "✗ Miss" if rev_act and rev_est and float(rev_act) < float(rev_est) else "—"
        except (ValueError, TypeError):
            eps_beat = rev_beat = "—"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #2c3e50;">{ticker} Earnings Report - {period}</h2>
            
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Financial Results</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="border-bottom: 1px solid #dee2e6;">
                        <td style="padding: 8px;"><strong>EPS:</strong></td>
                        <td style="padding: 8px;">Estimate: {eps_est}</td>
                        <td style="padding: 8px;">Actual: {eps_act}</td>
                        <td style="padding: 8px; color: {'green' if 'Beat' in eps_beat else 'red' if 'Miss' in eps_beat else 'gray'};">{eps_beat}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px;"><strong>Revenue:</strong></td>
                        <td style="padding: 8px;">Estimate: {rev_est}</td>
                        <td style="padding: 8px;">Actual: {rev_act}</td>
                        <td style="padding: 8px; color: {'green' if 'Beat' in rev_beat else 'red' if 'Miss' in eps_beat else 'gray'};">{rev_beat}</td>
                    </tr>
                </table>
            </div>
            
            <div style="margin: 20px 0;">
                <h3>AI-Generated Insights</h3>
                <div style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; border-radius: 4px;">
                    {ai_insights.replace(chr(10), '<br>')}
                </div>
            </div>
            
            <div style="margin: 20px 0;">
                <h3>Recent News</h3>
                <ul>
                    {chr(10).join([f'<li><a href="{item.get("url", "#")}" target="_blank">{item.get("headline", "N/A")}</a></li>' for item in news_data[:3]])}
                </ul>
            </div>
            
            <div style="margin-top: 30px; padding: 15px; background: #e9ecef; border-radius: 4px; font-size: 12px; color: #6c757d;">
                Generated by Smart Earnings Agent on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def send_email(self, subject, html_content):
        """Send email"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_user
            msg['To'] = self.email_to
            msg['Subject'] = subject
            
            # Create plain text version
            text_content = html_content.replace('<br>', '\n').replace('<li>', '• ').replace('</li>', '')
            text_content = text_content.replace('<strong>', '').replace('</strong>', '')
            text_content = text_content.replace('<h2>', '\n\n').replace('</h2>', '\n')
            text_content = text_content.replace('<h3>', '\n').replace('</h3>', '\n')
            text_content = text_content.replace('<div>', '').replace('</div>', '')
            text_content = text_content.replace('<table>', '').replace('</table>', '')
            text_content = text_content.replace('<tr>', '').replace('</tr>', '')
            text_content = text_content.replace('<td>', ' | ').replace('</td>', '')
            text_content = text_content.replace('<ul>', '').replace('</ul>', '')
            text_content = text_content.replace('<a href="', '').replace('" target="_blank">', ': ')
            text_content = text_content.replace('</a>', '')
            
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
        """Main execution with smart batching and fallback"""
        print("🚀 Starting Smart Earnings Agent with OpenAI Best Practices...")
        
        # Determine date to check
        if test_mode:
            target_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"📅 Checking earnings for: {target_date}")
        
        # Load tickers
        tickers = self.load_tickers()
        if not tickers:
            print("❌ No tickers loaded. Exiting.")
            return
        
        # Collect all data first
        print("\n📊 Collecting earnings data and news...")
        tickers_data = {}
        
        for i, ticker in enumerate(tickers, 1):
            print(f"\n--- Collecting data for {ticker} ({i}/{len(tickers)}) ---")
            
            # Get earnings data
            earnings = self.get_earnings_data(ticker, target_date)
            if not earnings:
                continue
            
            # Get news
            news = self.get_company_news(ticker, target_date)
            
            # Store data for batch processing
            tickers_data[ticker] = {
                'earnings': earnings,
                'news': news
            }
            
            # Rate limiting between API calls
            if i < len(tickers):
                time.sleep(1)
        
        if not tickers_data:
            print("❌ No earnings data found. Exiting.")
            return
        
        print(f"\n🤖 Generating AI insights for {len(tickers_data)} tickers...")
        print("💡 Using OpenAI best practices: token optimization, smart batching, and fallback strategies")
        
        # Try batch processing first, fallback to individual if needed
        ai_insights = self.generate_batched_ai_insights(tickers_data)
        
        print(f"\n📧 Sending emails...")
        
        # Send emails
        emails_sent = 0
        
        for ticker, data in tickers_data.items():
            print(f"\n--- Sending email for {ticker} ---")
            
            # Create and send email
            subject = f"{ticker} Earnings Report - {data['earnings'].get('period', 'Unknown')}"
            html_content = self.create_email_content(ticker, data['earnings'], data['news'], ai_insights.get(ticker, 'No insights available'))
            
            if self.send_email(subject, html_content):
                emails_sent += 1
        
        print(f"\n🎉 Processing complete! Sent {emails_sent} emails for {target_date}")
        print("✅ AI insights generated successfully using OpenAI SDK")

def main():
    """Main entry point"""
    import sys
    
    test_mode = True
    
    try:
        agent = EarningsAgent()
        agent.run(test_mode=test_mode)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()