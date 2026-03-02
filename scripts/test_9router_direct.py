#!/usr/bin/env python3
"""Test 9router endpoint directly with requests."""

import os
import json
import requests

api_key = os.getenv("LLM_API_KEY")
url = "https://9router.on.nickroth.com/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

payload = {
    "model": "balance",
    "messages": [{"role": "user", "content": "Say 'hello'"}],
    "max_tokens": 32,
}

print(f"Testing endpoint: {url}")
print(f"Model: balance")
print(f"Headers: {headers}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print()

try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response headers: {dict(response.headers)}")
    print()

    try:
        data = response.json()
        print(f"Response JSON:")
        print(json.dumps(data, indent=2))
    except:
        print(f"Raw response:")
        print(response.text)

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
