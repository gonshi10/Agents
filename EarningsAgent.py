#!/usr/bin/env python3
"""
Smart Earnings Agent - Intelligent Stock Earnings Monitor with AI Insights
- Automatically fetches earnings data for stocks in watchlist.csv
- Uses AI to generate comprehensive summaries and insights
- Sends detailed email reports for each earnings announcement
- Smart API batching and rate limiting
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
load_dotenv()

class EarningsAgent:
    def __init__(self):
        # Load environment variables
        self.finnhub_key = os.getenv('FINNHUB_API_KEY')
        self.openai_key = os.getenv('OPENAI_API_KEY')
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_pass = os.getenv('SMTP_PASS')
        self.email_to = os.getenv('EMAIL_TO')
        
        # OpenAI rate limiting settings
        self.openai_calls_per_minute = 3  # Conservative limit
        self.last_openai_call = 0
        self.openai_call_times = []
        
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
            
            # Filter for earnings-related news
            relevant_news = []
            for item in news:
                headline = item.get('headline', '').lower()
                if any(keyword in headline for keyword in ['earnings', 'quarterly', 'results', 'guidance']):
                    relevant_news.append(item)
            
            print(f"✓ Found {len(relevant_news)} relevant news items for {ticker}")
            return relevant_news[:5]  # Limit to top 5
            
        except Exception as e:
            print(f"✗ Failed to get news for {ticker}: {e}")
            return []
    
    def wait_for_openai_rate_limit(self):
        """Wait if we're hitting OpenAI rate limits"""
        now = time.time()
        
        # Remove calls older than 1 minute
        self.openai_call_times = [t for t in self.openai_call_times if now - t < 60]
        
        # If we've made too many calls recently, wait
        if len(self.openai_call_times) >= self.openai_calls_per_minute:
            wait_time = 60 - (now - self.openai_call_times[0]) + random.uniform(1, 5)
            print(f"⏳ OpenAI rate limit reached. Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            now = time.time()
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0.5, 2.0)
        time.sleep(jitter)
        
        self.openai_call_times.append(now)
        self.last_openai_call = now
    
    def generate_batched_ai_insights(self, tickers_data):
        """Generate AI insights for multiple tickers in one API call"""
        if not self.openai_key:
            return {ticker: "AI insights disabled - set OPENAI_API_KEY to enable" for ticker in tickers_data.keys()}
        
        try:
            # Wait for rate limiting
            self.wait_for_openai_rate_limit()
            
            # Build context for all tickers
            context = "Please analyze the following earnings results and provide 2-3 key insights for each company:\n\n"
            
            for ticker, data in tickers_data.items():
                earnings = data['earnings']
                news = data['news']
                
                context += f"""
{ticker}:
- Period: {earnings.get('period', 'Unknown')}
- EPS: Est {earnings.get('epsEstimate', 'N/A')} vs Actual {earnings.get('epsActual', 'N/A')}
- Revenue: Est {earnings.get('revenueEstimate', 'N/A')} vs Actual {earnings.get('revenueActual', 'N/A')}
- News: {', '.join([item.get('headline', 'N/A')[:50] for item in news[:2]])}

"""
            
            context += "\nProvide insights in this format:\nTICKER: [2-3 bullet points]\nTICKER: [2-3 bullet points]\n..."
            
            headers = {
                'Authorization': f'Bearer {self.openai_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'gpt-4o-mini',
                'messages': [
                    {'role': 'system', 'content': 'You are a financial analyst. Provide concise, actionable insights for each company.'},
                    {'role': 'user', 'content': context}
                ],
                'max_tokens': 800,
                'temperature': 0.3
            }
            
            response = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            data = response.json()
            content = data['choices'][0]['message']['content']
            
            print(f"✓ Generated AI insights for {len(tickers_data)} tickers in one API call")
            
            # Parse the response to extract insights for each ticker
            insights = {}
            current_ticker = None
            current_insights = []
            
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line starts with a ticker symbol
                if any(ticker in line.upper() for ticker in tickers_data.keys()):
                    # Save previous ticker's insights
                    if current_ticker:
                        insights[current_ticker] = '\n'.join(current_insights) if current_insights else "No insights available"
                    
                    # Start new ticker
                    current_ticker = line.split(':')[0].strip().upper()
                    current_insights = []
                elif current_ticker and line.startswith('-'):
                    current_insights.append(line)
                elif current_ticker and line:
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
            return {ticker: f"AI insights unavailable: {str(e)}" for ticker in tickers_data.keys()}
    
    def create_email_content(self, ticker, earnings_data, news_data, ai_insights):
        """Create email content"""
        eps_est = earnings_data.get('epsEstimate', 'N/A')
        eps_act = earnings_data.get('epsActual', 'N/A')
        rev_est = earnings_data.get('revenueEstimate', 'N/A')
        rev_act = earnings_data.get('revenueActual', 'N/A')
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
                        <td style="padding: 8px; color: {'green' if 'Beat' in rev_beat else 'red' if 'Miss' in rev_beat else 'gray'};">{rev_beat}</td>
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
        """Main execution with smart batching"""
        print("🚀 Starting Smart Earnings Agent...")
        
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
        
        # Generate AI insights in batches
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