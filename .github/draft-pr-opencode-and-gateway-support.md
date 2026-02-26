## Draft PR: Add OpenCode Backend Support + OpenAI-Compatible LLM Endpoints + Task-Specific Models

**Status:** Draft - Ready for Review  
**Branch:** `feat/multi-backend-support` → `main`  
**Related:** Closes #[issue number]

### Summary
This PR adds comprehensive backend flexibility to ApplyPilot:

1. **OpenCode CLI Backend** - Alternative to Claude Code for auto-apply orchestration
2. **OpenAI-Compatible LLM Endpoints** - Support for gateways, routers, LiteLLM, Ollama
3. **Task-Specific Model Configuration** - Different models for different use cases (scoring vs tailoring)
4. **Documentation Updates** - Claude Code is default, OpenCode is alternative option

**Claude Code remains the DEFAULT backend.** OpenCode is available as an opt-in alternative via `APPLY_BACKEND=opencode`.

### Changes

#### 1. Auto-Apply Backend Abstraction
- **New:** `src/applypilot/apply/backends.py` (802 lines)
  - `AgentBackend` abstract base class
  - `ClaudeBackend` - Claude Code CLI integration (DEFAULT)
  - `OpenCodeBackend` - OpenCode CLI integration (alternative)
  - `get_backend()` factory with `APPLY_BACKEND` env var support
  - Unified output parsing and status taxonomy

- **Refactored:** `src/applypilot/apply/launcher.py`
  - Integrated backend abstraction layer
  - **Backward compatible** - defaults to Claude if `APPLY_BACKEND` unset

#### 2. OpenAI-Compatible LLM Endpoints
- **Enhanced:** `src/applypilot/llm.py`
  - `LLM_URL` environment variable support
  - Priority: `LLM_URL` > Gemini > OpenAI
  - Supports any OpenAI-compatible API (gateways, LiteLLM, Ollama, AI routers)
  - Automatic fallback from OpenAI-compatible to native Gemini API

#### 3. Task-Specific Model Configuration (NEW)
- **Enhanced:** `src/applypilot/llm.py`
  - Per-task model selection via environment variables
  - Constants for default models to avoid duplication:
    - `DEFAULT_FLASH_MODEL = "gemini-2.0-flash"` (most tasks)
    - `DEFAULT_PRO_MODEL = "gemini-2.5-pro"` (high-quality tasks)
  - OpenAI defaults mapped from Gemini equivalents
  - New API: `get_client_for_task(task_name)`

**Environment Variables:**
```bash
# Task-specific model overrides
SCORING_MODEL=gemini-2.0-flash        # Fast, cheap for job scoring
TAILORING_MODEL=gemini-2.5-pro        # High quality for resume writing
COVER_LETTER_MODEL=gemini-2.0-flash   # Standard for cover letters
JD_PARSE_MODEL=gemini-2.0-flash       # Fast for JD extraction
RESUME_MATCH_MODEL=gemini-2.0-flash   # Fast for gap analysis
VALIDATION_MODEL=gemini-2.0-flash     # Fast for validation
ENRICHMENT_MODEL=gemini-2.0-flash     # Fast for job enrichment
SMART_EXTRACT_MODEL=gemini-2.0-flash  # Fast for smart extraction
```

**Priority Order:**
1. `TASK_MODEL` env var (e.g., `TAILORING_MODEL=gpt-4`)
2. `LLM_MODEL` env var (generic override)
3. Task default from `TASK_MODEL_DEFAULTS`
4. Provider default

**OpenAI Model Mapping:**
- `gemini-2.0-flash` → `gpt-5-mini` (default for most tasks)
- `gemini-2.5-pro` → `gpt-5` (for high-quality tasks)

#### 4. Test Suite
- **New:** `tests/test_backend_selection.py` (30 tests)
- **New:** `tests/test_provider_routing.py` (19 tests)
- **Total:** 49 tests, all passing

#### 5. Documentation Updates
- **Updated:** `README.md` - Claude default clearly stated, OpenCode as alternative
- **Updated:** `.env.example` - All new env vars documented
- **New:** `opencode.json` - MCP parity configuration

### Configuration Examples

#### Default (Claude Code - no changes needed)
```bash
# No configuration needed - Claude is default
applypilot apply
```

#### Use OpenCode (alternative)
```bash
export APPLY_BACKEND=opencode
export APPLY_OPENCODE_MODEL="gh/claude-sonnet-4.5"
export APPLY_OPENCODE_AGENT="coder"

# Register MCP servers first
opencode mcp add my-mcp --provider=openai --url "$LLM_URL" --api-key "$LLM_API_KEY" --model "$LLM_MODEL"

applypilot apply
```

#### Use OpenAI-Compatible Gateway
```bash
export LLM_URL="https://my-gateway.example.com/v1"
export LLM_API_KEY="sk-xxxxxxxx"
export LLM_MODEL="gpt-4o-mini"
```

#### Task-Specific Models
```bash
# Use cheap model for scoring, powerful model for tailoring
export SCORING_MODEL=gpt-5-mini
export TAILORING_MODEL=gpt-5
export COVER_LETTER_MODEL=claude-sonnet-4

applypilot run  # Uses different models for each stage
```

### Personal Use Case: OpenAI-Compatible Router

The author personally uses an OpenAI-compatible AI router with fallback support, which enables utilizing multiple LLM subscriptions (GitHub Copilot, Kimi Code, ChatGPT) through a unified endpoint. Any OpenAI-compatible endpoint should work with these changes.

**Example router capabilities:**
- Provides OpenAI-compatible API at `https://router.example.com/v1`
- Fallback chain: primary → secondary → tertiary providers
- Single API key routes to multiple backend providers
- Cost optimization and redundancy across subscriptions

### Future Considerations

**Agent Framework with Memory Backend:**
A future enhancement could leverage an agent framework that supports a memory backend to better support learning preferences:
- Per-role learning (what works for different role types)
- Per-company learning (what resonates with specific companies)
- Global learning (universal best practices across all applications)
- Persistent feedback loop to improve tailoring over time

**Standard OpenAI Variables:**
Currently uses `LLM_URL`, `LLM_API_KEY`, `LLM_MODEL`. A future refactor could consider using standard OpenAI SDK environment variables:
- `OPENAI_BASE_URL` instead of `LLM_URL`
- `OPENAI_API_KEY` instead of `LLM_API_KEY`

**LLM-Agnostic Layer:**
Future work should consider migrating to an LLM-agnostic layer with a simpler interface so any provider can be supported with a more uniform configuration.

**Note:** Anthropic API-compatible endpoint support would require different environment variables and is not included in this PR.

### Testing

```bash
# Backend selection tests
pytest tests/test_backend_selection.py -v  # 30 tests

# Provider routing tests  
pytest tests/test_provider_routing.py -v     # 19 tests

# All tests
pytest tests/ -v                              # 225+ tests total
```

### Migration Guide

**No migration required.** Existing users continue using Claude Code by default without any changes.

**To try OpenCode:**
```bash
export APPLY_BACKEND=opencode
applypilot doctor  # Verify setup
applypilot apply
```

**To use a gateway:**
```bash
export LLM_URL="https://gateway.example.com/v1"
export LLM_API_KEY="sk-xxxxx"
applypilot run  # Uses gateway for LLM calls
```

**To customize models:**
```bash
export TAILORING_MODEL=gpt-4  # Use different model for tailoring
applypilot run
```

### Environment Variables Reference

**LLM Provider Selection (priority order):**
1. `LLM_URL` + `LLM_API_KEY` - OpenAI-compatible gateway
2. `GEMINI_API_KEY` - Google Gemini (recommended default)
3. `OPENAI_API_KEY` - OpenAI direct

**Auto-Apply Backend:**
- `APPLY_BACKEND` - `claude` (default) or `opencode`
- `APPLY_CLAUDE_MODEL` - Default: `haiku`
- `APPLY_OPENCODE_MODEL` - Fallback to `LLM_MODEL` or `gpt-4o-mini`
- `APPLY_OPENCODE_AGENT` - Passed as `--agent` to `opencode run`

**Task-Specific Models:**
- `SCORING_MODEL` - Fast model for job scoring (default: gemini-2.0-flash/gpt-5-mini)
- `TAILORING_MODEL` - High-quality for resume writing (default: gemini-2.5-pro/gpt-5)
- `COVER_LETTER_MODEL` - Standard for cover letters
- `JD_PARSE_MODEL` - Fast for JD extraction
- `RESUME_MATCH_MODEL` - Fast for gap analysis
- `VALIDATION_MODEL` - Fast for validation checks
- `ENRICHMENT_MODEL` - Fast for job enrichment
- `SMART_EXTRACT_MODEL` - Fast for smart extraction

### Checklist
- [x] Code follows project style
- [x] Tests added and passing (49 new, 225+ total)
- [x] Documentation updated (Claude default clearly stated)
- [x] Backward compatible (no breaking changes)
- [x] OpenAI-compatible endpoint support via LLM_URL
- [x] Task-specific model configuration
- [x] Constants used for default models (no duplication)
- [ ] Integration tested with real OpenCode applications (pending)
- [ ] Integration tested with real gateway (pending)

### Architecture Decisions

1. **Claude remains default** - No user impact, zero migration
2. **OpenCode is opt-in** - Must explicitly set `APPLY_BACKEND=opencode`
3. **LLM_URL has priority** - Gateway overrides direct API keys for flexibility
4. **Unified interface** - Same status taxonomy regardless of backend
5. **No MCP config per-invocation** - OpenCode manages MCPs globally
6. **Task-specific models** - Flexibility to optimize cost vs quality per task
7. **Constants for defaults** - Easy to change, no string duplication

---

**Ready for review when:**
1. Maintainer approves architecture
2. Upstream confirms no conflicting backend work
3. Integration tests pass with real backends
4. Task-specific model selection validated
