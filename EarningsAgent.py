#!/usr/bin/env python3
"""
Smart Earnings Agent - Intelligent Stock Earnings Monitor with AI Insights
- Automatically fetches earnings data for stocks in watchlist.csv
- Uses AI to generate comprehensive summaries and insights
- Sends detailed email reports for each earnings announcement
- Simple rate limiting with delays between API calls
- Built-in error handling and reliability
- insights
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
        self.max_tokens_per_request = 600  # Increased for richer insights
        self.max_input_tokens = 2000  # Limit input size
        
        # Caching to avoid duplicate API calls
        self.insights_cache = {}
        self.sector_cache = {}  # Cache for company sectors
        
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
    
    def get_company_sector(self, ticker):
        """Get company sector/industry and map to expert type"""
        # Check cache first
        if ticker in self.sector_cache:
            return self.sector_cache[ticker]
        
        try:
            # Check rate limit before making API call
            self.check_rate_limit()
            
            url = "https://finnhub.io/api/v1/stock/profile2"
            params = {
                'token': self.finnhub_key,
                'symbol': ticker
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            sector = data.get('finnhubIndustry', '').upper() if data.get('finnhubIndustry') else ''
            industry = data.get('finnhubIndustry', '').upper() if data.get('finnhubIndustry') else ''
            
            # Map sector/industry to expert type
            expert_type = self.map_sector_to_expert(sector, industry, ticker)
            
            # Cache the result
            self.sector_cache[ticker] = expert_type
            
            print(f"✓ Determined sector expert for {ticker}: {expert_type}")
            return expert_type
            
        except Exception as e:
            print(f"⚠️ Failed to get sector for {ticker}: {e}, using fallback")
            # Fallback to ticker-based mapping
            expert_type = self.map_sector_to_expert('', '', ticker)
            self.sector_cache[ticker] = expert_type
            return expert_type
    
    def map_sector_to_expert(self, sector, industry, ticker):
        """Map sector/industry to expert type"""
        sector_lower = sector.lower() if sector else ''
        industry_lower = industry.lower() if industry else ''
        
        # Technology sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'technology', 'tech', 'software', 'hardware', 'semiconductor', 'internet', 
            'cloud', 'saas', 'ai', 'artificial intelligence', 'cybersecurity'
        ]):
            return 'Tech Analyst'
        
        # Healthcare sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'healthcare', 'health', 'pharmaceutical', 'biotech', 'biotechnology', 
            'medical', 'pharma', 'drug', 'therapeutic'
        ]):
            return 'Healthcare Specialist'
        
        # Energy sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'energy', 'oil', 'gas', 'petroleum', 'renewable', 'solar', 'wind', 
            'utilities', 'power'
        ]):
            return 'Energy Expert'
        
        # Financial sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'financial', 'finance', 'banking', 'bank', 'insurance', 'investment', 
            'capital', 'credit', 'lending'
        ]):
            return 'Financial Services Analyst'
        
        # Consumer sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'consumer', 'retail', 'consumer goods', 'consumer discretionary', 
            'consumer staples', 'retail', 'e-commerce'
        ]):
            return 'Consumer Goods Analyst'
        
        # Industrial sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'industrial', 'manufacturing', 'machinery', 'aerospace', 'defense', 
            'construction', 'engineering'
        ]):
            return 'Industrial Analyst'
        
        # Real Estate sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'real estate', 'reit', 'property', 'realty'
        ]):
            return 'Real Estate Analyst'
        
        # Communication/Media sector mapping
        if any(keyword in sector_lower or keyword in industry_lower for keyword in [
            'communication', 'telecom', 'media', 'entertainment', 'broadcasting'
        ]):
            return 'Media & Communications Analyst'
        
        # Fallback: Use common ticker-based mapping for well-known stocks
        tech_tickers = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX', 'AMD', 'INTC']
        healthcare_tickers = ['JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR']
        financial_tickers = ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK']
        
        if ticker in tech_tickers:
            return 'Tech Analyst'
        elif ticker in healthcare_tickers:
            return 'Healthcare Specialist'
        elif ticker in financial_tickers:
            return 'Financial Services Analyst'
        
        # Default fallback
        return 'General Financial Analyst'
    
    def optimize_context_for_tokens(self, tickers_data):
        """Optimize context to stay within token limits with enhanced guidance analysis"""
        def format_number(value):
            if value is None or value == 'N/A':
                return 'N/A'
            try:
                return f"{float(value):.2f}"
            except (ValueError, TypeError):
                return str(value)
        
        optimized_context = """Analyze earnings results and provide comprehensive, structured insights for each company. For each company, provide:

1. EXECUTIVE SUMMARY: 2-3 sentence overview of strategic implications and key takeaways. DO NOT restate EPS/revenue numbers (those are already shown in the Financial Results section). Focus on what the results mean strategically, competitive implications, or forward-looking significance. If you would only restate the numbers, skip this section or provide meaningful strategic insights instead.
2. STRATEGIC ANALYSIS: Deep dive into what the numbers mean for competitive position, market share, and future growth trajectory
3. RISK FACTORS: Identify key risks (operational, financial, market, regulatory) and how management is addressing them
4. INVESTMENT RECOMMENDATION: Clear recommendation (STRONG BUY / BUY / HOLD / SELL / STRONG SELL) with confidence level (High/Medium/Low) and brief reasoning
5. EXPERT RECOMMENDATION: Which sector expert type should review this company (e.g., Tech Analyst, Healthcare Specialist, Energy Expert)

Format your response as:
TICKER:
EXECUTIVE SUMMARY: [2-3 sentences of strategic insights - NOT just restating numbers]
STRATEGIC ANALYSIS: [2-3 sentences]
RISK FACTORS: [2-3 key risks]
INVESTMENT RECOMMENDATION: [RECOMMENDATION] ([CONFIDENCE]) - [brief reasoning]
EXPERT RECOMMENDATION: [Expert Type]

Avoid stating the obvious (e.g., "EPS increased"). Focus on strategic insights, forward-looking implications, and actionable analysis. The Executive Summary should provide strategic context, not repeat financial metrics.

"""
        
        for ticker, data in tickers_data.items():
            earnings = data['earnings']
            news = data['news']
            
            # Get sector/expert type
            expert_type = self.get_company_sector(ticker)
            
            # Extract guidance insights
            guidance_insights = self.extract_guidance_insights(news)
            
            # Create comprehensive context with guidance focus
            context_line = f"""{ticker} (Sector Expert: {expert_type}):
EPS: {format_number(earnings.get('epsEstimate'))}→{format_number(earnings.get('epsActual'))} 
Revenue: {format_number(earnings.get('revenueEstimate'))}→{format_number(earnings.get('revenueActual'))}
Guidance & Strategic Context: {' | '.join(guidance_insights) if guidance_insights else 'Limited guidance available'}

"""
            optimized_context += context_line
        
        return optimized_context
    
    def generate_ai_insights_single(self, ticker, earnings_data, news_data):
        """Generate AI insights for a single ticker using OpenAI SDK with enhanced structured analysis"""
        if not self.openai_client:
            return {
                'summary': 'AI insights disabled - set OPENAI_API_KEY to enable',
                'strategic_analysis': '',
                'risk_factors': '',
                'investment_recommendation': 'N/A',
                'expert_recommendation': 'General Financial Analyst'
            }
        
        # Check cache first
        cache_key = f"{ticker}_{earnings_data.get('epsActual', 'N/A')}"
        if cache_key in self.insights_cache:
            print(f"✓ Using cached insights for {ticker}")
            cached = self.insights_cache[cache_key]
            # Return cached data (could be dict or string)
            if isinstance(cached, dict):
                return cached
            else:
                # Parse old format if needed
                return self.parse_structured_insights(cached, ticker)
        
        try:
            # Wait for rate limiting
            self.wait_for_openai_rate_limit()
            
            # Get sector/expert type
            expert_type = self.get_company_sector(ticker)
            
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
Analyze earnings results for {ticker} (Sector Expert: {expert_type}):

EPS: Est {format_number(earnings_data.get('epsEstimate'))} vs Actual {format_number(earnings_data.get('epsActual'))}
Revenue: Est {format_number(earnings_data.get('revenueEstimate'))} vs Actual {format_number(earnings_data.get('revenueActual'))}

News: {', '.join([item.get('headline', 'N/A')[:50] for item in news_data[:2]])}

Provide comprehensive, structured insights:
1. EXECUTIVE SUMMARY: 2-3 sentence overview of strategic implications and key takeaways. DO NOT restate EPS/revenue numbers (those are already shown). Focus on what the results mean strategically, competitive implications, or forward-looking significance. If you would only restate the numbers, skip this section or provide meaningful strategic insights instead.
2. STRATEGIC ANALYSIS: What the results mean strategically
3. RISK FACTORS: Key risks identified
4. INVESTMENT RECOMMENDATION: Clear Buy/Hold/Sell with confidence level
5. EXPERT RECOMMENDATION: Which sector expert should review (already identified as {expert_type}, confirm or suggest alternative)

Format:
EXECUTIVE SUMMARY: [strategic insights - NOT just restating numbers]
STRATEGIC ANALYSIS: [content]
RISK FACTORS: [content]
INVESTMENT RECOMMENDATION: [RECOMMENDATION] ([CONFIDENCE]) - [reasoning]
EXPERT RECOMMENDATION: [Expert Type]
"""
            
            print(f"🤖 Generating enhanced AI insights for {ticker}...")
            
            # Use OpenAI SDK with enhanced prompt
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior financial analyst specializing in earnings analysis and strategic insights. You excel at identifying forward-looking guidance, strategic implications, risk factors, and investment theses. Provide decisive, actionable recommendations with clear reasoning. Avoid obvious statements and focus on sophisticated, informative analysis."},
                    {"role": "user", "content": context}
                ],
                max_tokens=self.max_tokens_per_request
            )
            
            content = response.choices[0].message.content
            
            # Parse structured response
            parsed_insights = self.parse_structured_insights(content, ticker)
            
            # Cache the result
            self.insights_cache[cache_key] = parsed_insights
            
            print(f"✓ Generated enhanced AI insights for {ticker}")
            return parsed_insights
            
        except Exception as e:
            print(f"✗ AI insights failed for {ticker}: {e}")
            return {
                'summary': f'AI insights unavailable: {str(e)}',
                'strategic_analysis': '',
                'risk_factors': '',
                'investment_recommendation': 'N/A',
                'expert_recommendation': self.get_company_sector(ticker)
            }
    
    def generate_batched_ai_insights(self, tickers_data):
        """Generate AI insights for multiple tickers in one API call using OpenAI SDK"""
        if not self.openai_client:
            default_insight = {
                'summary': 'AI insights disabled - set OPENAI_API_KEY to enable',
                'strategic_analysis': '',
                'risk_factors': '',
                'investment_recommendation': 'N/A',
                'expert_recommendation': 'General Financial Analyst'
            }
            return {ticker: default_insight for ticker in tickers_data.keys()}
        
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
                    {"role": "system", "content": "You are a senior financial analyst specializing in earnings analysis and strategic insights. You excel at identifying forward-looking guidance, strategic implications, risk factors, and investment theses. Provide decisive, actionable recommendations with clear reasoning. For each company, provide structured insights covering executive summary, strategic analysis, risk factors, investment recommendation, and expert recommendation. Avoid obvious statements and focus on sophisticated, informative analysis."},
                    {"role": "user", "content": context}
                ],
                max_tokens=self.max_tokens_per_request * len(tickers_data)  # Scale tokens with ticker count
            )
            
            content = response.choices[0].message.content
            
            # Debug: Show the raw AI response
            print(f"✓ Generated AI insights for {len(tickers_data)} tickers in one API call")
            
            # Parse the response to extract structured insights for each ticker
            insights = {}
            current_ticker = None
            current_ticker_content = []
            
            # Split by ticker sections
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if this line starts with a ticker symbol
                ticker_found = None
                for ticker in tickers_data.keys():
                    if line.upper().startswith(ticker.upper() + ':') or line.upper().startswith(ticker.upper() + ' '):
                        ticker_found = ticker
                        break
                
                if ticker_found:
                    # Save previous ticker's insights
                    if current_ticker and current_ticker_content:
                        ticker_text = '\n'.join(current_ticker_content)
                        insights[current_ticker] = self.parse_structured_insights(ticker_text, current_ticker)
                    
                    # Start new ticker
                    current_ticker = ticker_found
                    current_ticker_content = []
                    # Add the ticker line if it has content after the ticker
                    if ':' in line:
                        remaining = line.split(':', 1)[1].strip()
                        if remaining:
                            current_ticker_content.append(remaining)
                elif current_ticker:
                    # Add to current ticker's content
                    current_ticker_content.append(line)
            
            # Save last ticker's insights
            if current_ticker and current_ticker_content:
                ticker_text = '\n'.join(current_ticker_content)
                insights[current_ticker] = self.parse_structured_insights(ticker_text, current_ticker)
            
            # Fill in any missing tickers with parsed insights from full text
            for ticker in tickers_data.keys():
                if ticker not in insights:
                    # Try to find ticker content in the full response
                    insights[ticker] = self.parse_structured_insights(content, ticker)
            
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
            # generate_ai_insights_single now returns a dict, so we can use it directly
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
    
    def _is_meaningful_summary(self, summary_text):
        """Check if summary contains meaningful insights vs just restating stats"""
        if not summary_text or len(summary_text.strip()) < 50:
            return False
        
        summary_lower = summary_text.lower()
        
        # Check for strategic keywords
        strategic_keywords = [
            'implication', 'strategic', 'competitive', 'market', 'outlook', 
            'guidance', 'position', 'growth', 'trajectory', 'advantage',
            'challenge', 'opportunity', 'trend', 'shift', 'momentum',
            'resilience', 'strength', 'weakness', 'headwind', 'tailwind',
            'environment', 'landscape', 'dynamics', 'cycle', 'phase'
        ]
        
        # Check if it's just restating stats
        stat_phrases = [
            'eps of', 'revenue of', 'beat expectations', 'missed expectations',
            'earnings per share', 'reported revenue', 'actual eps', 'actual revenue',
            'estimated', 'vs actual', 'vs estimate', 'compared to'
        ]
        
        has_strategic_content = any(keyword in summary_lower for keyword in strategic_keywords)
        
        # Count how many stat phrases appear
        stat_phrase_count = sum(1 for phrase in stat_phrases if phrase in summary_lower)
        
        # If it has multiple stat phrases and no strategic content, it's likely just restating stats
        is_just_stats = stat_phrase_count >= 2 and not has_strategic_content
        
        # Also check if it's too short and only contains numbers/stat language
        if len(summary_text) < 100 and stat_phrase_count >= 1 and not has_strategic_content:
            return False
        
        return has_strategic_content or (not is_just_stats and len(summary_text) > 100)
    
    def _format_insights_html(self, summary, strategic_analysis, risk_factors):
        """Format insights sections as HTML"""
        sections = []
        
        # Only include Executive Summary if it contains meaningful insights
        if summary and self._is_meaningful_summary(summary):
            sections.append(f'''
                    <div class="insight-section">
                        <h4>📋 Executive Summary</h4>
                        <p>{summary}</p>
                    </div>
                    ''')
        
        if strategic_analysis:
            sections.append(f'''
                    <div class="insight-section">
                        <h4>🎯 Strategic Analysis</h4>
                        <p>{strategic_analysis}</p>
                    </div>
                    ''')
        
        if risk_factors:
            sections.append(f'''
                    <div class="insight-section">
                        <h4>⚠️ Risk Factors</h4>
                        <p>{risk_factors}</p>
                    </div>
                    ''')
        
        if not sections:
            sections.append(f'''
                    <div class="insight-section">
                        <p>{summary if summary else "No insights available"}</p>
                    </div>
                    ''')
        
        return ''.join(sections)
    
    def parse_structured_insights(self, response_text, ticker):
        """Parse AI response into structured format"""
        # Default values
        result = {
            'summary': '',
            'strategic_analysis': '',
            'risk_factors': '',
            'investment_recommendation': 'HOLD (Medium Confidence)',
            'expert_recommendation': self.get_company_sector(ticker)
        }
        
        if not response_text:
            return result
        
        # Try to parse structured format
        lines = response_text.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                    current_content = []
                continue
            
            # Check for section headers
            if 'EXECUTIVE SUMMARY' in line.upper():
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                current_section = 'summary'
                current_content = []
                # Extract content after colon if present
                if ':' in line:
                    content = line.split(':', 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif 'STRATEGIC ANALYSIS' in line.upper():
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                current_section = 'strategic_analysis'
                current_content = []
                if ':' in line:
                    content = line.split(':', 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif 'RISK FACTORS' in line.upper() or 'RISK FACTOR' in line.upper():
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                current_section = 'risk_factors'
                current_content = []
                if ':' in line:
                    content = line.split(':', 1)[1].strip()
                    if content:
                        current_content.append(content)
            elif 'INVESTMENT RECOMMENDATION' in line.upper():
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                current_section = 'investment_recommendation'
                current_content = []
                if ':' in line:
                    content = line.split(':', 1)[1].strip()
                    if content:
                        result['investment_recommendation'] = content
                        current_section = None
            elif 'EXPERT RECOMMENDATION' in line.upper():
                if current_section and current_content:
                    result[current_section] = ' '.join(current_content)
                if ':' in line:
                    content = line.split(':', 1)[1].strip()
                    if content:
                        result['expert_recommendation'] = content
                current_section = None
            elif current_section:
                # Continue adding to current section
                current_content.append(line)
        
        # Save last section
        if current_section and current_content:
            result[current_section] = ' '.join(current_content)
        
        # Fallback: if no structured format found, treat as summary
        if not result['summary'] and not result['strategic_analysis']:
            result['summary'] = response_text[:500]  # First 500 chars as summary
        
        return result
    
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
        
        # Handle structured insights (dict) or legacy format (string)
        if isinstance(ai_insights, dict):
            summary = ai_insights.get('summary', 'No summary available')
            strategic_analysis = ai_insights.get('strategic_analysis', 'No strategic analysis available')
            risk_factors = ai_insights.get('risk_factors', 'No risk factors identified')
            investment_rec = ai_insights.get('investment_recommendation', 'HOLD (Medium Confidence)')
            expert_rec = ai_insights.get('expert_recommendation', 'General Financial Analyst')
        else:
            # Legacy string format - convert to structured
            summary = str(ai_insights) if ai_insights else 'No insights available'
            strategic_analysis = ''
            risk_factors = ''
            investment_rec = 'HOLD (Medium Confidence)'
            expert_rec = self.get_company_sector(ticker)
        
        # Parse investment recommendation for styling
        rec_upper = investment_rec.upper()
        if 'STRONG BUY' in rec_upper or 'STRONG BUY' in rec_upper:
            rec_class = 'strong-buy'
            rec_color = '#28a745'
            rec_bg = '#d4edda'
        elif 'BUY' in rec_upper:
            rec_class = 'buy'
            rec_color = '#20c997'
            rec_bg = '#d1ecf1'
        elif 'SELL' in rec_upper or 'STRONG SELL' in rec_upper:
            rec_class = 'sell'
            rec_color = '#dc3545'
            rec_bg = '#f8d7da'
        else:
            rec_class = 'hold'
            rec_color = '#ffc107'
            rec_bg = '#fff3cd'
        
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
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
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
                    line-height: 1.8;
                }}
                .insights p {{
                    margin: 0 0 15px 0;
                }}
                .insights p:last-child {{
                    margin-bottom: 0;
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
                .recommendation-badge {{
                    display: inline-block;
                    padding: 12px 24px;
                    border-radius: 25px;
                    font-weight: bold;
                    font-size: 1.1em;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    margin: 10px 0;
                }}
                .recommendation-badge.strong-buy {{
                    background: #d4edda;
                    color: #155724;
                    border: 2px solid #c3e6cb;
                }}
                .recommendation-badge.buy {{
                    background: #d1ecf1;
                    color: #0c5460;
                    border: 2px solid #bee5eb;
                }}
                .recommendation-badge.hold {{
                    background: #fff3cd;
                    color: #856404;
                    border: 2px solid #ffeaa7;
                }}
                .recommendation-badge.sell {{
                    background: #f8d7da;
                    color: #721c24;
                    border: 2px solid #f5c6cb;
                }}
                .expert-badge {{
                    display: inline-block;
                    padding: 8px 16px;
                    border-radius: 20px;
                    background: #e7f3ff;
                    color: #004085;
                    border: 2px solid #b3d7ff;
                    font-weight: 600;
                    margin: 10px 0;
                }}
                .insight-section {{
                    margin-bottom: 20px;
                }}
                .insight-section h4 {{
                    margin: 0 0 10px 0;
                    color: #495057;
                    font-size: 1.1em;
                    font-weight: 600;
                }}
                .insight-section p {{
                    margin: 0;
                    line-height: 1.6;
                    color: #333;
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
                                <div class="progress-fill {'beat' if 'BEAT' in rev_beat else 'miss' if 'MISS' in rev_beat else '50%'}"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">💡 Investment Recommendation</h3>
                <div style="text-align: center;">
                    <div class="recommendation-badge {rec_class}">
                        {investment_rec}
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">👤 Expert Recommendation</h3>
                <div style="text-align: center;">
                    <div class="expert-badge">
                        {expert_rec}
                    </div>
                    <p style="margin-top: 10px; color: #6c757d; font-size: 0.9em;">
                        Recommended expert type for detailed sector-specific analysis
                    </p>
                </div>
            </div>
            
            <div class="card">
                <h3 style="margin-top: 0; color: #495057;">🧠 AI Insights</h3>
                <div class="insights">
                    {self._format_insights_html(summary, strategic_analysis, risk_factors)}
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
            
            # Handle structured insights for plain text
            if isinstance(ai_insights, dict):
                summary_text = ai_insights.get('summary', 'No summary available')
                strategic_text = ai_insights.get('strategic_analysis', '')
                risks_text = ai_insights.get('risk_factors', '')
                rec_text = ai_insights.get('investment_recommendation', 'HOLD')
                expert_text = ai_insights.get('expert_recommendation', 'General Financial Analyst')
                insights_text = f"""
EXECUTIVE SUMMARY:
{summary_text}

STRATEGIC ANALYSIS:
{strategic_text if strategic_text else 'No strategic analysis available'}

RISK FACTORS:
{risks_text if risks_text else 'No risk factors identified'}

INVESTMENT RECOMMENDATION: {rec_text}
EXPERT RECOMMENDATION: {expert_text}
"""
            else:
                insights_text = str(ai_insights).replace('<br>', '\n').replace('<strong>', '').replace('</strong>', '')
            
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
 {insights_text}
 
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
            target_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
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
            
            # Get insights for this ticker (handle both dict and string formats)
            ticker_insights = ai_insights.get(ticker, {})
            if not isinstance(ticker_insights, dict):
                # Legacy format - create default dict
                ticker_insights = {
                    'summary': str(ticker_insights) if ticker_insights else 'No insights available',
                    'strategic_analysis': '',
                    'risk_factors': '',
                    'investment_recommendation': 'HOLD (Medium Confidence)',
                    'expert_recommendation': self.get_company_sector(ticker)
                }
            
            # Create and send email
            subject = f"{ticker} Earnings Report"
            html_content = self.create_email_content(ticker, data['earnings'], data['news'], ticker_insights)
            
            if self.send_email(ticker, subject, html_content, data['earnings'], data['news'], ticker_insights):
                emails_sent += 1
        
        print(f"\n🎉 Processing complete! Sent {emails_sent} emails for {target_date}")
        print("✅ Simple rate limiting implemented successfully")

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