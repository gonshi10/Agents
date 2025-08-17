#!/usr/bin/env python3
"""
Test script to debug AI insights generation
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

def test_ai_insights():
    """Test AI insights generation step by step using OpenAI SDK"""
    print("🧪 TESTING AI INSIGHTS GENERATION (OpenAI SDK)")
    print("=" * 60)
    
    # Load environment
    load_dotenv()
    
    # Check OpenAI key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("❌ OpenAI API key not set")
        return
    
    print(f"✅ OpenAI API key found: {openai_key[:10]}...")
    
    # Test basic OpenAI SDK
    print("\n📡 Testing OpenAI SDK...")
    
    try:
        from openai import OpenAI
        
        print("📡 Initializing OpenAI SDK client...")
        client = OpenAI(api_key=openai_key)
        
        print("📤 Sending test request via SDK...")
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "user", "content": "Say 'Hello, this is a test'"}
            ],
            max_completion_tokens=50
        )
        
        content = response.choices[0].message.content
        print(f"✅ OpenAI SDK working! Response: {content}")
        
        # Test with actual earnings data
        print("\n🧪 Testing with mock earnings data...")
        test_earnings_data = {
            'period': 'Q1 2024',
            'epsEstimate': '1.50',
            'epsActual': '1.75',
            'revenueEstimate': '1000000000',
            'revenueActual': '1100000000'
        }
        
        test_news_data = [
            {'headline': 'Company beats earnings expectations'},
            {'headline': 'Strong revenue growth reported'}
        ]
        
        # Test the actual context that would be sent
        context = f"""
Analyze earnings results for AAPL:

Period: {test_earnings_data.get('period', 'Unknown')}
EPS: Est {test_earnings_data.get('epsEstimate', 'N/A')} vs Actual {test_earnings_data.get('epsActual', 'N/A')}
Revenue: Est {test_earnings_data.get('revenueEstimate', 'N/A')} vs Actual {test_earnings_data.get('revenueActual', 'N/A')}

News: {', '.join([item.get('headline', 'N/A')[:50] for item in test_news_data[:2]])}

Provide 2-3 key insights in bullet points.
"""
        
        print(f"📝 Context to be sent:")
        print(f"Length: {len(context)} characters")
        print(f"Content: {context[:200]}...")
        
        # Test the actual API call that would be made
        print("\n📤 Testing actual earnings analysis via SDK...")
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "You are a financial analyst. Provide concise, actionable insights."},
                {"role": "user", "content": context}
            ],
            max_completion_tokens=300
        )
        
        content = response.choices[0].message.content
        print(f"✅ Earnings analysis working! Response:")
        print(f"   {content}")
        
    except Exception as e:
        print(f"❌ Error testing OpenAI SDK: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_insights()
