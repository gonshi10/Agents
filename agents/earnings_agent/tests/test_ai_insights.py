#!/usr/bin/env python3
"""Simple end-to-end OpenAI test for prompt formatting."""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def test_ai_insights() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY is not set")
        return

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": "You are a financial analyst."},
            {
                "role": "user",
                "content": "Analyze this: EPS 1.5->1.7, Revenue 1B->1.1B. Give concise insights.",
            },
        ],
        max_tokens=200,
    )
    print("✅ AI response:", response.choices[0].message.content)


if __name__ == "__main__":
    test_ai_insights()

