# CRITICAL UPDATE - ApplyPilot Workaround Found

## Issue Identified in ApplyPilot Codebase

The ApplyPilot codebase already contains a **documented workaround** for this exact issue with 9router and LiteLLM!

### Location
File: `/Users/nroth/workspace/ApplyPilot/src/applypilot/llm.py`

### Root Cause (From Code Comments)
```python
# Line 256-258 in llm.py:
# NOTE: Don't pass timeout - some custom endpoints (9router) return
# streaming format when timeout is passed, causing parse errors
```

**The issue is that passing the `timeout` parameter to custom endpoints (like 9router) causes them to return streaming format (SSE) instead of JSON, even when `stream=False` is set!**

### ApplyPilot's Workaround

**1. Detect Custom Endpoints** (Line 151-152):
```python
# Use OpenAI client directly for custom endpoints (workaround for LiteLLM bug)
self._use_openai_direct = config.api_base is not None and config.provider == "openai"
```

**2. Use OpenAI Client Directly** (Line 183-190):
```python
# Use OpenAI client directly for custom endpoints (workaround for LiteLLM bug)
if self._use_openai_direct and self._openai_client:
    return self._chat_openai_direct(
        messages=messages,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
        **extra,
    )
```

**3. Omit Timeout in Direct Calls** (Line 252-258):
```python
kwargs: dict[str, Any] = {
    "model": model_name,
    "messages": messages,
    "max_tokens": max_output_tokens,
    # NOTE: Don't pass timeout - some custom endpoints (9router) return
    # streaming format when timeout is passed, causing parse errors
}
```

### The Fix

When using custom OpenAI-compatible endpoints like 9router:
- **DO NOT pass the `timeout` parameter**
- Use the OpenAI Python client directly instead of LiteLLM
- Or if using LiteLLM, ensure `timeout` is not passed in the request

---

## Updated Recommendations

### Immediate Fix for 9router

**If you're using LiteLLM directly:**
```python
# DON'T DO THIS (causes streaming format response):
response = litellm.completion(
    model="openai/your-model",
    messages=messages,
    stream=False,
    timeout=120,  # ❌ This causes 9router to return SSE format!
    api_base="https://9router-endpoint/v1",
)

# DO THIS instead:
response = litellm.completion(
    model="openai/your-model",
    messages=messages,
    stream=False,
    # ❌ NO timeout parameter!
    api_base="https://9router-endpoint/v1",
)
```

**If using ApplyPilot's LLMClient:**
The workaround is already implemented! When you set `LLM_URL` (which sets `api_base`), ApplyPilot automatically:
1. Uses the OpenAI client directly (bypassing LiteLLM)
2. Omits the `timeout` parameter from the request

### Why Timeout Causes This Issue

The 9router endpoint (and potentially other custom OpenAI-compatible proxies) appears to have a bug or non-standard behavior where:
- When `timeout` is passed in the request body/params, it triggers streaming mode
- This is NOT standard OpenAI API behavior
- It's likely a parameter name collision or misconfiguration in the proxy

---

## Updated Solution Summary

| Approach | Solution |
|----------|----------|
| **Use ApplyPilot's LLMClient** | Already fixed - uses OpenAI client directly and omits timeout |
| **Use LiteLLM directly** | Don't pass `timeout` parameter to custom endpoints |
| **Use OpenAI client directly** | Don't pass `timeout` parameter |
| **Test with curl** | Verify endpoint behavior without timeout: `curl ... -d '{...}'` (no timeout field) |

---

## Files Referenced in ApplyPilot

- `/Users/nroth/workspace/ApplyPilot/src/applypilot/llm.py` - Contains the workaround
- `/Users/nroth/workspace/ApplyPilot/scripts/test_9router_nostream.py` - Test script
- `/Users/nroth/workspace/ApplyPilot/scripts/debug_timeout.py` - Demonstrates timeout issue

---

**END OF CRITICAL UPDATE**

---


# LiteLLM Custom OpenAI-Compatible Endpoint Issues - Research Findings

## Summary

The issue where LiteLLM receives streaming format (SSE) responses from a custom endpoint (9router) even when `stream=False` is set, causing `'str' object has no attribute 'choices'` errors, is a known pattern with LiteLLM when working with custom OpenAI-compatible endpoints.

---

## Key Findings

### 1. Known LiteLLM Issues with Custom OpenAI-Compatible Endpoints

#### Issue #19700: `drop_params` Field Doesn't Work
- **Status**: Closed (completed)
- **Problem**: When using custom OpenAI-compatible endpoints, LiteLLM adds extra metadata parameters (like `metadata`) that the custom endpoint doesn't support
- **Impact**: Causes 400 Bad Request errors from custom endpoints
- **Example Error**: `{"detail":"Unsupported parameter: metadata"}`

#### Issue #21090: Responses API Streaming Falls Back to Fake Stream
- **Status**: Open
- **Problem**: For custom models not in LiteLLM's model database, the Responses API falls back to "fake streaming" which silently drops events
- **Root Cause**: `supports_native_streaming()` returns `False` for unknown models, triggering fake streaming
- **Impact**: Tool call events, function calls, and streaming chunks are dropped

#### Issue #20711: Responses API Streaming Drops Tool Call Argument Deltas
- **Status**: Closed
- **Problem**: Streaming iterator skips chunks where `id` is `None`, losing ~90% of tool call argument delta events
- **Code Location**: `litellm/responses/litellm_completion_transformation/streaming_iterator.py:145-148`

#### Issue #1659: OpenRouter Streaming AttributeError
- **Status**: Closed
- **Problem**: `'NoneType' object has no attribute 'content'` when streaming from OpenRouter
- **Code Location**: `litellm/utils.py:7513` - `handle_openai_chat_completion_chunk`
- **Root Cause**: Assumes `choices[0].delta.content` exists without null checking

---

### 2. How LiteLLM Handles the `stream` Parameter

#### Documentation Findings:
- LiteLLM uses the `stream` parameter to determine if responses should be streamed
- When `stream=True`, LiteLLM expects SSE (Server-Sent Events) format responses
- When `stream=False`, LiteLLM expects standard JSON responses with a `choices` array

#### Key Code Paths:
1. **Completion Function**: `litellm.completion()` accepts `stream` parameter
2. **Chunk Processing**: `handle_openai_chat_completion_chunk()` in `utils.py` processes streaming chunks
3. **Response Parsing**: Assumes response has `choices` attribute with array of choice objects

#### Critical Behavior:
```python
# From documentation - LiteLLM expects this format for non-streaming:
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!"
      }
    }
  ]
}
```

---

### 3. Special Configuration for Custom Endpoints

#### Required Configurations:

**1. Use `drop_params=True`**
```yaml
model_list:
  - model_name: my-custom-model
    litellm_params:
      model: openai/my-model-name
      api_base: https://9router-endpoint/v1
      api_key: your-api-key
      drop_params: true  # 👈 Drop unsupported params
```

**2. Use `additional_drop_params` for Specific Parameters**
```yaml
litellm_settings:
  drop_params: True
  additional_drop_params: ["metadata", "user_api_key", "user_api_key_user_id"]
```

**3. Configure Custom API Base**
```python
import litellm
litellm.api_base = "https://9router-endpoint/v1"
# OR via environment variable
os.environ['OPENAI_BASE_URL'] = "https://9router-endpoint/v1"
```

**4. Use `openai/` Prefix for OpenAI-Compatible Endpoints**
```yaml
model_list:
  - model_name: my-model
    litellm_params:
      model: openai/custom-model-name  # 👈 openai/ prefix required
      api_base: https://9router-endpoint/v1
```

---

### 4. Common Issues with LiteLLM and OpenAI-Compatible Proxies/Gateways

#### Issue #1: Response Format Mismatch
**Problem**: LiteLLM receives streaming format (SSE) when expecting JSON, or vice versa
**Root Causes**:
- Proxy/gateway ignores `stream: false` in request
- LiteLLM's internal handling forces streaming for certain providers
- Custom endpoint returns different format than expected

#### Issue #2: Metadata Parameters
**Problem**: LiteLLM adds internal metadata fields that custom endpoints reject
**Fields Often Rejected**:
- `metadata.user_api_key_hash`
- `metadata.user_api_key_user_id`
- `metadata.litellm_api_version`
- `metadata.endpoint`

#### Issue #3: Model Recognition
**Problem**: Unknown models trigger fallback behavior (fake streaming, parameter validation errors)
**Solution**: 
- Use `model_info` to register custom models
- Set `supports_native_streaming: true` in model configuration

#### Issue #4: Parameter Passing
**Problem**: LiteLLM passes OpenAI-specific parameters to custom endpoints that don't support them
**Solution**: Use `drop_params` and `additional_drop_params` aggressively

---

## Root Cause Analysis for Your Issue

The `'str' object has no attribute 'choices'` error indicates:

1. **LiteLLM expects a JSON object** with a `choices` array (non-streaming format)
2. **Instead, it's receiving a string** - likely:
   - An SSE line (e.g., `data: {...}`)
   - A raw text response from the endpoint
   - An error message as a plain string

3. **Why this happens with 9router**:
   - 9router may be ignoring the `stream: false` parameter
   - 9router may be returning SSE format even for non-streaming requests
   - LiteLLM's OpenAI handler may be incorrectly detecting the response format

---

## Recommended Solutions

### Solution 1: Force Non-Streaming Mode (Immediate Fix)
```python
import litellm
from litellm import completion

# Ensure stream is explicitly False and use raw response
response = completion(
    model="openai/your-model-name",
    messages=messages,
    stream=False,  # Explicitly disable streaming
    api_base="https://9router-endpoint/v1",
    drop_params=True,  # Drop unsupported params
    additional_drop_params=["metadata", "stream_options"]
)
```

### Solution 2: Configure LiteLLM Proxy with Drop Params
```yaml
# config.yaml
model_list:
  - model_name: 9router-model
    litellm_params:
      model: openai/9router-model
      api_base: https://9router-endpoint/v1
      api_key: os.environ/NINE_ROUTER_API_KEY
      drop_params: true
      additional_drop_params: 
        - "metadata"
        - "stream_options"
        - "user"
        - "temperature"  # if not supported

litellm_settings:
  drop_params: true
  set_verbose: true  # Enable debugging

general_settings:
  master_key: sk-your-proxy-key
```

### Solution 3: Use Custom HTTP Handler (Advanced)
```python
import httpx
import litellm

# Create custom client with specific headers
client = httpx.Client(
    base_url="https://9router-endpoint/v1",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
)

litellm.client_session = client

# Make request ensuring no streaming
response = litellm.completion(
    model="openai/custom-model",
    messages=messages,
    stream=False
)
```

### Solution 4: Check 9router Endpoint Behavior
```bash
# Test directly with curl to verify 9router behavior
curl -X POST https://9router-endpoint/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "model": "your-model",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```

If 9router returns SSE format even with `stream: false`, the issue is on 9router's side.

### Solution 5: Workaround - Handle Both Formats
```python
import litellm
from litellm import completion

def safe_completion(*args, **kwargs):
    """Wrapper to handle both streaming and non-streaming responses"""
    try:
        # Try non-streaming first
        kwargs['stream'] = False
        response = completion(*args, **kwargs)
        
        # Check if response is a string (unexpected streaming format)
        if isinstance(response, str):
            # Parse SSE format manually
            lines = response.strip().split('\n')
            for line in lines:
                if line.startswith('data: '):
                    data = line[6:]  # Remove 'data: ' prefix
                    if data == '[DONE]':
                        break
                    # Parse JSON chunk
                    import json
                    chunk = json.loads(data)
                    if 'choices' in chunk:
                        return chunk
        
        return response
    except AttributeError as e:
        if "'str' object has no attribute 'choices'" in str(e):
            # Fallback to streaming mode
            kwargs['stream'] = True
            return completion(*args, **kwargs)
        raise
```

---

## Debugging Steps

1. **Enable Verbose Logging**:
   ```python
   litellm.set_verbose = True
   ```

2. **Check Request/Response**:
   ```python
   litellm.return_response_headers = True
   response = completion(...)
   print(response._response_headers)
   ```

3. **Use Debug Proxy**:
   ```bash
   litellm --config config.yaml --detailed_debug
   ```

4. **Verify Raw Response**:
   ```python
   import httpx
   raw_response = httpx.post(
       "https://9router-endpoint/v1/chat/completions",
       headers={"Authorization": f"Bearer {api_key}"},
       json={"model": "your-model", "messages": messages, "stream": False}
   )
   print(raw_response.text)  # Check what 9router actually returns
   ```

---

## Related GitHub Issues

- **#19700**: [drop_params field doesn't work](https://github.com/BerriAI/litellm/issues/19700)
- **#21090**: [Responses API streaming falls back to fake stream](https://github.com/BerriAI/litellm/issues/21090)
- **#20711**: [Responses API Streaming Drops Tool Call Argument Deltas](https://github.com/BerriAI/litellm/issues/20711)
- **#1659**: [OpenRouter streaming AttributeError](https://github.com/BerriAI/litellm/issues/1659)
- **#15370**: [curl success but litellm fail](https://github.com/BerriAI/litellm/issues/15370)
- **#22073**: [MCP proxy buffers SSE responses](https://github.com/BerriAI/litellm/issues/22073)

---

## Conclusion

The issue stems from LiteLLM's assumption that custom endpoints fully comply with OpenAI's API specification. When `stream=False` is set but the endpoint returns streaming format (SSE), LiteLLM fails to parse the response correctly.

**Recommended immediate action**:
1. Use `drop_params=True` and `additional_drop_params` to strip unsupported fields
2. Test 9router directly with curl to verify it respects `stream: false`
3. If 9router always returns SSE, consider using LiteLLM in streaming mode (`stream=True`) and handling the streaming iterator properly
4. Report the issue to LiteLLM with specific details about 9router's behavior

**Long-term solution**:
- Request LiteLLM add better support for custom endpoints that deviate from strict OpenAI compliance
- Consider using a more compliant proxy layer between LiteLLM and 9router
