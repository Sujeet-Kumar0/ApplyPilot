#!/usr/bin/env python3
"""Debug LLMClient with detailed output."""

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

from applypilot.llm import LLMConfig, LLMClient

config = LLMConfig(
    provider="openai",
    api_base="https://9router.on.nickroth.com/v1",
    model="openai/balance",
    api_key=os.getenv("LLM_API_KEY", ""),
)

print(f"Config: {config}")

client = LLMClient(config)
print(f"_use_openai_direct: {client._use_openai_direct}")
print(f"_openai_client: {client._openai_client}")

# Try calling _chat_openai_direct directly
print("\nCalling _chat_openai_direct directly...")
try:
    result = client._chat_openai_direct(
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_output_tokens=32,
        temperature=0.0,
    )
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
