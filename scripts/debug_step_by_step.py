#!/usr/bin/env python3
"""Debug LLMClient step by step."""

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

# Import everything as LLMClient does
from openai import OpenAI
from applypilot.llm import LLMConfig

print("Step 1: Create config")
config = LLMConfig(
    provider="openai",
    api_base="https://9router.on.nickroth.com/v1",
    model="openai/balance",
    api_key=os.getenv("LLM_API_KEY", ""),
)
print(f"  Config: {config}")

print("\nStep 2: Create OpenAI client directly")
openai_client = OpenAI(
    base_url=config.api_base,
    api_key=config.api_key or "",
)
print(f"  Client type: {type(openai_client)}")

print("\nStep 3: Call chat.completions.create")
kwargs = {
    "model": "balance",
    "messages": [{"role": "user", "content": "Say 'hello'"}],
    "max_tokens": 32,
    "timeout": 120,
}
print(f"  kwargs: {kwargs}")

response = openai_client.chat.completions.create(**kwargs)
print(f"  Response type: {type(response)}")
print(f"  Response: {response}")

print("\nStep 4: Access choices")
if hasattr(response, "choices"):
    content = response.choices[0].message.content
    print(f"  Content: {content}")
else:
    print(f"  ERROR: Response has no 'choices' attribute!")
    print(f"  Response value: {response}")
