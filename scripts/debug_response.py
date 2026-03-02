#!/usr/bin/env python3
"""Debug OpenAI client response type."""

import os
from openai import OpenAI

client = OpenAI(
    base_url="https://9router.on.nickroth.com/v1",
    api_key=os.getenv("LLM_API_KEY", ""),
)

print(f"Client type: {type(client)}")

response = client.chat.completions.create(
    model="balance",
    messages=[{"role": "user", "content": "Say 'hello'"}],
    max_tokens=32,
    stream=False,
)

print(f"Response type: {type(response)}")
print(f"Response: {response}")
print(f"Response repr: {repr(response)[:500]}")

if hasattr(response, "choices"):
    print(f"Choices: {response.choices}")
    print(f"Content: {response.choices[0].message.content}")
else:
    print("Response has no 'choices' attribute")
