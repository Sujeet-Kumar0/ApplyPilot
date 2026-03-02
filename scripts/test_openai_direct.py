#!/usr/bin/env python3
"""Test 9router with OpenAI client directly."""

import os
from openai import OpenAI

client = OpenAI(
    base_url="https://9router.on.nickroth.com/v1",
    api_key=os.getenv("LLM_API_KEY"),
)

try:
    response = client.chat.completions.create(
        model="balance",
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_tokens=32,
        stream=False,
    )
    print(f"✅ Success!")
    print(f"Response: {response.choices[0].message.content}")
    print(f"Model used: {response.model}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
