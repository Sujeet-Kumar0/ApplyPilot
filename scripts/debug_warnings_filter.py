#!/usr/bin/env python3
"""Debug - test warnings filter effect."""

import os
import sys
from pathlib import Path
import warnings

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

# Import litellm and set things up like llm.py does
import litellm

litellm.suppress_debug_info = True
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")

from openai import OpenAI

client = OpenAI(
    base_url="https://9router.on.nickroth.com/v1",
    api_key=os.getenv("LLM_API_KEY", ""),
)

print("\nTest: After all llm.py setup")
response = client.chat.completions.create(
    model="balance",
    messages=[{"role": "user", "content": "Say 'hello'"}],
    max_tokens=32,
    timeout=120,
    stream=False,
)
print(f"  Response type: {type(response)}")
if hasattr(response, "choices"):
    print(f"  Content: {response.choices[0].message.content}")
else:
    print(f"  ERROR: Got string response!")
