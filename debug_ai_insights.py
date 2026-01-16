#!/usr/bin/env python3
"""
Debug script to test AI insights generation
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def test_openai_connection():
    """Test OpenAI connection and API key"""
    openai_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    
    print(f"OpenAI API Key: {'✓ Set' if openai_key else '✗ Not set'}")
    print(f"Model: {model}")
    
    if not openai_key:
        print("❌ No OpenAI API key found!")
        return False
    
    try:
        client = OpenAI(api_key=openai_key)
        print("✅ OpenAI client created successfully")
        
        # Test a simple API call
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'Hello, AI insights are working!'"}
            ],
            max_tokens=50
        )
        
        content = response.choices[0].message.content
        print(f"✅ OpenAI API test successful: {content}")
        return True
        
    except Exception as e:
        print(f"❌ OpenAI API test failed: {e}")
        return False

def test_ai_insights_generation():
    """Test AI insights generation with mock data"""
    if not test_openai_connection():
        return
    
    openai_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    client = OpenAI(api_key=openai_key)
    
    # Mock tickers data similar to what the real code would have
    mock_tickers_data = {
        'AAPL': {
            'earnings': {
                'epsEstimate': '1.50',
                'epsActual': '1.65',
                'revenueEstimate': '85000000000',
                'revenueActual': '89000000000'
            },
            'news': [
                {'headline': 'Apple Reports Strong Q3 Results, Beats Expectations'},
                {'headline': 'Apple Provides Upbeat Guidance for Holiday Quarter'},
                {'headline': 'Apple Announces New Strategic Initiatives'}
            ]
        },
        'MSFT': {
            'earnings': {
                'epsEstimate': '2.20',
                'epsActual': '2.35',
                'revenueEstimate': '55000000000',
                'revenueActual': '58000000000'
            },
            'news': [
                {'headline': 'Microsoft Cloud Revenue Surges'},
                {'headline': 'Microsoft Expands AI Capabilities'},
                {'headline': 'Microsoft Announces Strategic Partnerships'}
            ]
        }
    }
    
    print("\n🧪 Testing AI insights generation...")
    
    try:
        # Test the same prompt structure as the real code
        system_prompt = "You are a senior financial analyst specializing in earnings analysis and strategic insights. You excel at identifying forward-looking guidance, strategic implications, and investment theses. For each company, provide 3-4 sophisticated insights that focus on guidance analysis, strategic implications, risk factors, and investment thesis. Avoid obvious statements and focus on sophisticated analysis."
        
        # Create context similar to what optimize_context_for_tokens would create
        context = """Analyze earnings results and provide sophisticated, forward-looking insights for each company. Focus on:

1. GUIDANCE ANALYSIS: Extract and analyze forward-looking statements, outlook, and strategic initiatives
2. STRATEGIC IMPLICATIONS: What the numbers mean for future growth, market position, and competitive advantage
3. RISK FACTORS: Identify potential challenges and how management is addressing them
4. INVESTMENT THESIS: Why investors should care beyond the obvious beats/misses

Avoid stating the obvious (e.g., "EPS increased"). Instead, focus on strategic insights and guidance implications.

Format: TICKER: [3-4 sophisticated insights with guidance analysis]

AAPL: 
EPS: 1.50→1.65 
Revenue: 85000000000→89000000000
Guidance & Strategic Context: GUIDANCE: Apple Provides Upbeat Guidance for Holiday Quarter | STRATEGIC: Apple Announces New Strategic Initiatives

MSFT: 
EPS: 2.20→2.35 
Revenue: 55000000000→58000000000
Guidance & Strategic Context: STRATEGIC: Microsoft Expands AI Capabilities | STRATEGIC: Microsoft Announces Strategic Partnerships

"""
        
        print("📤 Sending request to OpenAI...")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            max_tokens=600
        )
        
        content = response.choices[0].message.content
        print(f"✅ AI insights generated successfully!")
        print(f"\n📝 Raw AI Response:")
        print("=" * 50)
        print(content)
        print("=" * 50)
        
        # Test parsing logic
        print(f"\n🔍 Testing parsing logic...")
        insights = {}
        current_ticker = None
        current_insights = []
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts with a ticker symbol
            ticker_found = None
            for ticker in mock_tickers_data.keys():
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
                print(f"  Found ticker: {ticker_found}")
            elif current_ticker and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                current_insights.append(line)
                print(f"    Added insight: {line[:50]}...")
            elif current_ticker and line:
                # If line doesn't start with bullet but has content, treat as insight
                current_insights.append(f"• {line}")
                print(f"    Added insight: • {line[:50]}...")
        
        # Save last ticker's insights
        if current_ticker:
            insights[current_ticker] = '\n'.join(current_insights) if current_insights else "No insights available"
        
        # Fill in any missing tickers
        for ticker in mock_tickers_data.keys():
            if ticker not in insights:
                insights[ticker] = "AI insights unavailable"
        
        print(f"\n📊 Parsed Insights:")
        for ticker, insight in insights.items():
            print(f"\n{ticker}:")
            print(f"  {insight[:100]}{'...' if len(insight) > 100 else ''}")
        
        return True
        
    except Exception as e:
        print(f"❌ AI insights generation failed: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Debugging AI Insights Generation")
    print("=" * 40)
    
    test_ai_insights_generation()

