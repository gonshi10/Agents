#!/usr/bin/env python3
"""
Configuration file for Earnings Agent
"""

import os
from typing import Optional

LOCAL = True
if LOCAL:
    from dotenv import load_dotenv
    load_dotenv()

class Config:
    """Centralized configuration for the Earnings Agent"""
    
    # API Keys
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # OpenAI Settings
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.25"))
    
    # Email Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    EMAIL_TO: str = os.getenv("EMAIL_TO", "")
    
    # File Paths
    WATCHLIST_CSV: str = os.getenv("WATCHLIST_CSV", "./watchlist.csv")
    
    # Runtime Settings
    TEST_MODE: bool = os.getenv("TEST_MODE", "false").lower() == "true"
    
    # API Rate Limiting
    API_DELAY_SECONDS: float = float(os.getenv("API_DELAY_SECONDS", "1.0"))
    
    # Content Limits
    MAX_PRESS_TEXT_LENGTH: int = int(os.getenv("MAX_PRESS_TEXT_LENGTH", "8000"))
    MAX_GUIDANCE_LINES: int = int(os.getenv("MAX_GUIDANCE_LINES", "8"))
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate required configuration and return list of missing items"""
        missing = []
        
        if not cls.FINNHUB_API_KEY:
            missing.append("FINNHUB_API_KEY")
        if not cls.SMTP_USER:
            missing.append("SMTP_USER")
        if not cls.SMTP_PASS:
            missing.append("SMTP_PASS")
        if not cls.EMAIL_TO:
            missing.append("EMAIL_TO")
            
        return missing
    
    @classmethod
    def print_summary(cls):
        """Print configuration summary for debugging"""
        print("=== Earnings Agent Configuration ===")
        print(f"Finnhub API: {'✓' if cls.FINNHUB_API_KEY else '✗'}")
        print(f"OpenAI API: {'✓' if cls.OPENAI_API_KEY else '✗'}")
        print(f"SMTP: {'✓' if cls.SMTP_USER and cls.SMTP_PASS else '✗'}")
        print(f"Email To: {'✓' if cls.EMAIL_TO else '✗'}")
        print(f"Watchlist: {cls.WATCHLIST_CSV}")
        print(f"Test Mode: {cls.TEST_MODE}")
        print(f"Local Mode: {cls.LOCAL_MODE}")
        print("==================================") 