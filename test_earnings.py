#!/usr/bin/env python3
"""
Test script for Earnings Agent
"""

import os
import sys
from config import Config

def test_config():
    """Test configuration loading"""
    print("Testing configuration...")
    
    # Check if config can be loaded
    try:
        config = Config()
        print("✓ Configuration loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return False
    
    # Print configuration summary
    config.print_summary()
    
    # Validate required fields
    missing = config.validate()
    if missing:
        print(f"✗ Missing required configuration: {', '.join(missing)}")
        return False
    else:
        print("✓ All required configuration present")
    
    return True

def test_imports():
    """Test that all required modules can be imported"""
    print("\nTesting imports...")
    
    required_modules = [
        'csv', 'html', 'os', 're', 'smtplib', 'asyncio', 'aiohttp',
        'datetime', 'email.mime.multipart', 'email.mime.text',
        'typing', 'json', 'zoneinfo'
    ]
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError as e:
            print(f"✗ {module}: {e}")
            return False
    
    return True

def test_csv_loading():
    """Test CSV file loading"""
    print("\nTesting CSV loading...")
    
    csv_path = Config.WATCHLIST_CSV
    if not os.path.exists(csv_path):
        print(f"✗ CSV file not found: {csv_path}")
        return False
    
    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            tickers = []
            for row in reader:
                sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                if sym:
                    tickers.append(sym)
        
        if not tickers:
            print("✗ No tickers found in CSV")
            return False
        
        print(f"✓ Loaded {len(tickers)} tickers from CSV")
        print(f"  Sample tickers: {', '.join(tickers[:5])}")
        return True
        
    except Exception as e:
        print(f"✗ Failed to load CSV: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Earnings Agent Test Suite ===\n")
    
    tests = [
        ("Configuration", test_config),
        ("Imports", test_imports),
        ("CSV Loading", test_csv_loading),
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
        print("🎉 All tests passed! The Earnings Agent is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the configuration and dependencies.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 