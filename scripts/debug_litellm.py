#!/usr/bin/env python3
"""Debug LiteLLM with 9router endpoint."""

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

import litellm
from applypilot.llm import resolve_llm_config, LLMConfig, LLMClient

# Enable debug logging
litellm.set_verbose = True

print("=" * 60)
print("Debug: Testing 9router endpoint")
print("=" * 60)

# Test 1: Direct litellm call
print("\n🧪 Test 1: Direct litellm.completion() call...")
try:
    response = litellm.completion(
        model="openai/balance",
        api_base="https://9router.on.nickroth.com/v1",
        api_key=os.getenv("LLM_API_KEY"),
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_tokens=32,
        timeout=60,
    )
    print(f"✅ Direct call succeeded!")
    print(f"   Response type: {type(response)}")
    print(f"   Response: {response}")
except Exception as e:
    print(f"❌ Direct call failed: {e}")
    import traceback

    traceback.print_exc()

# Test 2: Using our LLMClient
print("\n🧪 Test 2: Using LLMClient...")
try:
    config = LLMConfig(
        provider="openai",
        api_base="https://9router.on.nickroth.com/v1",
        model="openai/balance",
        api_key=os.getenv("LLM_API_KEY", ""),
    )
    client = LLMClient(config)
    response = client.chat(
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_output_tokens=32,
    )
    print(f"✅ LLMClient call succeeded!")
    print(f"   Response: {response}")
except Exception as e:
    print(f"❌ LLMClient call failed: {e}")
    import traceback

    traceback.print_exc()

# Test 3: Try without the openai/ prefix
print("\n🧪 Test 3: Testing without openai/ prefix...")
try:
    response = litellm.completion(
        model="balance",  # No prefix
        api_base="https://9router.on.nickroth.com/v1",
        api_key=os.getenv("LLM_API_KEY"),
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_tokens=32,
        timeout=60,
    )
    print(f"✅ Call without prefix succeeded!")
    print(f"   Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ Call without prefix failed: {e}")

# Test 4: Try with gpt-4o-mini model
print("\n🧪 Test 4: Testing with gpt-4o-mini model...")
try:
    response = litellm.completion(
        model="openai/gpt-4o-mini",
        api_base="https://9router.on.nickroth.com/v1",
        api_key=os.getenv("LLM_API_KEY"),
        messages=[{"role": "user", "content": "Say 'hello'"}],
        max_tokens=32,
        timeout=60,
    )
    print(f"✅ gpt-4o-mini call succeeded!")
    print(f"   Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ gpt-4o-mini call failed: {e}")
