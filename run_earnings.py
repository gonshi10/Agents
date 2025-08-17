#!/usr/bin/env python3
"""
Simple runner script for Earnings Agent
"""

import os
import sys
import asyncio
from config import Config

async def run_agent():
    """Run the earnings agent"""
    try:
        from EarningsAgent import EarningsProcessor
        
        print("Starting Earnings Agent...")
        async with EarningsProcessor() as processor:
            await processor.run()
            
    except ImportError as e:
        print(f"Failed to import EarningsAgent: {e}")
        print("Make sure all dependencies are installed: pip install -r requirements.txt")
        return 1
    except Exception as e:
        print(f"Error running agent: {e}")
        return 1
    
    return 0

def main():
    """Main entry point"""
    # Set test mode if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        os.environ["TEST_MODE"] = "true"
        print("Running in TEST mode")
    
    # Set local mode if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--local":
        os.environ["LOCAL_MODE"] = "true"
        print("Running in LOCAL mode")
    
    # Run the agent
    return asyncio.run(run_agent())

if __name__ == "__main__":
    sys.exit(main()) 