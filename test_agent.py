#!/usr/bin/env python3
"""
Test script for Earnings Agent
"""

import os
import sys

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import csv
        import requests
        import smtplib
        from datetime import datetime, timedelta
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        print("✓ All required modules imported successfully")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")
    
    required_vars = ['FINNHUB_API_KEY', 'SMTP_USER', 'SMTP_PASS', 'EMAIL_TO']
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"✗ Missing environment variables: {', '.join(missing)}")
        print("Set these in your .env file or environment")
        return False
    else:
        print("✓ All required environment variables found")
        return True

def test_csv():
    """Test CSV file loading"""
    print("\nTesting CSV loading...")
    
    if not os.path.exists('watchlist.csv'):
        print("✗ watchlist.csv not found")
        return False
    
    try:
        import csv
        with open('watchlist.csv', 'r') as f:
            reader = csv.DictReader(f)
            tickers = []
            for row in reader:
                symbol = row.get('Symbol', '').strip().upper()
                if symbol:
                    tickers.append(symbol)
        
        if not tickers:
            print("✗ No tickers found in CSV")
            return False
        
        print(f"✓ Found {len(tickers)} tickers: {', '.join(tickers[:5])}")
        return True
        
    except Exception as e:
        print(f"✗ CSV loading failed: {e}")
        return False

def test_agent_import():
    """Test that EarningsAgent can be imported"""
    print("\nTesting EarningsAgent import...")
    
    try:
        from EarningsAgent import EarningsAgent
        print("✓ EarningsAgent imported successfully")
        return True
    except ImportError as e:
        print(f"✗ EarningsAgent import failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Earnings Agent Test Suite ===\n")
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("CSV Loading", test_csv),
        ("EarningsAgent Import", test_agent_import),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ {test_name} test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n=== Test Results ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Ready to run Earnings Agent.")
        print("\nTo run:")
        print("  python EarningsAgent.py --test")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
