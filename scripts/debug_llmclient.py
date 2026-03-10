#!/usr/bin/env python3
"""Debug LLMClient with 9router."""

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

from applypilot.llm import resolve_llm_config, LLMConfig, LLMClient

print("=" * 60)
print("Debug: Testing LLMClient with 9router")
print("=" * 60)

# Build config
config = LLMConfig(
    provider="openai",
    api_base="https://9router.on.nickroth.com/v1",
    model="openai/balance",
    api_key=os.getenv("LLM_API_KEY", ""),
)

print(f"\nConfig:")
print(f"  Provider: {config.provider}")
print(f"  Model: {config.model}")
print(f"  API Base: {config.api_base}")
print(f"  API Key: {'*' * 10}...")

client = LLMClient(config)
print(f"\nClient initialized:")
print(f"  _use_openai_direct: {client._use_openai_direct}")
print(f"  _openai_client: {client._openai_client}")

print("\n🧪 Sending test request...")
try:
    response = client.chat(
        messages=[{"role": "user", "content": "Say 'LiteLLM test passed' and nothing else."}],
        max_output_tokens=32,
        temperature=0.0,
    )
    print(f"✅ Success!")
    print(f"Response: {response}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
