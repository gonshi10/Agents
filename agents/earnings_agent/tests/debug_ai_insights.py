#!/usr/bin/env python3
"""Debug script for direct OpenAI connectivity."""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def test_openai_connection() -> bool:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    print(f"OpenAI API Key: {'✓ Set' if api_key else '✗ Not set'}")
    print(f"Model: {model}")
    if not api_key:
        return False
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'Hello, AI insights are working!'"}],
            max_tokens=50,
        )
        print("✅ OpenAI API test successful:", response.choices[0].message.content)
        return True
    except Exception as exc:
        print(f"❌ OpenAI API test failed: {exc}")
        return False


if __name__ == "__main__":
    test_openai_connection()

