#!/usr/bin/env python3
"""Debug OpenAI client in context of LLMClient."""

import os
import sys
from pathlib import Path

# Load .env from ~/.applypilot/
env_path = Path.home() / ".applypilot" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key, value)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Test OpenAI client directly in this context
from openai import OpenAI

client = OpenAI(
    base_url="https://9router.on.nickroth.com/v1",
    api_key=os.getenv("LLM_API_KEY", ""),
)

print(f"Client type: {type(client)}")
print(f"Client module: {type(client).__module__}")

response = client.chat.completions.create(
    model="balance",
    messages=[{"role": "user", "content": "Say 'hello'"}],
    max_tokens=32,
    stream=False,
)

print(f"\nResponse type: {type(response)}")
print(f"Response module: {type(response).__module__}")
print(f"Has choices: {hasattr(response, 'choices')}")

if hasattr(response, "choices"):
    print(f"Content: {response.choices[0].message.content}")
else:
    print(f"Response value: {response}")
