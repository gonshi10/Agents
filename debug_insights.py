#!/usr/bin/env python3
"""
Debug script to test AI insights generation specifically
"""

import os
from dotenv import load_dotenv

def test_ai_insights_generation():
    """Test just the AI insights generation"""
    print("🧪 DEBUGGING AI INSIGHTS GENERATION")
    print("=" * 50)
    
    # Load environment
    load_dotenv()
    
    try:
        from EarningsAgent import EarningsAgent
        
        print("✅ Successfully imported EarningsAgent")
        
        # Create agent
        agent = EarningsAgent()
        print("✅ Successfully created agent")
        
        # Test with mock data
        mock_tickers_data = {
            'AAPL': {
                'earnings': {
                    'period': 'Q1 2024',
                    'epsEstimate': '1.50',
                    'epsActual': '1.75',
                    'revenueEstimate': '1000000000',
                    'revenueActual': '1100000000'
                },
                'news': [
                    {'headline': 'Apple beats earnings expectations'},
                    {'headline': 'Strong iPhone sales reported'}
                ]
            }
        }
        
        print(f"\n📊 Testing with mock data for {len(mock_tickers_data)} ticker(s)")
        
        # Test single insights
        print("\n🔍 Testing single insights generation...")
        single_insight = agent.generate_ai_insights_single(
            'AAPL', 
            mock_tickers_data['AAPL']['earnings'], 
            mock_tickers_data['AAPL']['news']
        )
        print(f"Single insight result: {single_insight}")
        
        # Test batch insights
        print("\n🔍 Testing batch insights generation...")
        batch_insights = agent.generate_batched_ai_insights(mock_tickers_data)
        print(f"Batch insights result: {batch_insights}")
        
        print("\n✅ AI insights test completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_insights_generation()
