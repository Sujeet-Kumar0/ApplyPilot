## Draft PR: Multi-Backend LLM Support

**Status:** Draft - Ready for Review  
**Branch:** `feat/multi-backend-support` → `main`  
**Related:** Closes #[issue number]

### Summary
Adds pluggable backend architecture for the auto-apply launcher, enabling support for both Claude Code CLI and OpenCode CLI with unified output parsing and status taxonomy.

### Changes
- **New:** `src/applypilot/apply/backends.py` (802 lines)
  - `AgentBackend` abstract base class
  - `ClaudeBackend` implementation
  - `OpenCodeBackend` implementation  
  - `get_backend()` factory with env var support (`APPLY_BACKEND`)
  - Comprehensive error handling and status parsing

- **Refactored:** `src/applypilot/apply/launcher.py`
  - Integrated backend abstraction
  - Maintained backward compatibility (defaults to Claude)

- **New:** Test suite
  - `tests/test_backend_selection.py` (30 tests)
  - `tests/test_provider_routing.py` (19 tests)
  - Backend instantiation, selection, defaults, error cases

- **Updated:** Documentation
  - README: Backend configuration section
  - `.env.example`: New env vars
  - `opencode.json`: MCP parity config

### Environment Variables
```bash
# Select backend (claude|opencode, default: claude)
export APPLY_BACKEND=opencode

# OpenCode-specific
export APPLY_OPENCODE_MODEL=gh/claude-sonnet-4.5
export APPLY_OPENCODE_AGENT=coder

# Claude-specific
export APPLY_CLAUDE_MODEL=haiku
```

### Testing
```bash
pytest tests/test_backend_selection.py -v  # 30 tests
pytest tests/test_provider_routing.py -v     # 19 tests
```

### Checklist
- [x] Code follows project style
- [x] Tests added and passing (49 total)
- [x] Documentation updated
- [x] Backward compatible (defaults to Claude)
- [x] No breaking changes
- [ ] Integration tested with real applications (pending)

### Migration Guide
**No migration needed** - existing users continue using Claude by default. To switch:
```bash
export APPLY_BACKEND=opencode
opencode mcp add playwright --provider=...  # if not already configured
opencode mcp add gmail --provider=...       # if not already configured
applypilot apply
```

---

**Ready for review when:**
1. Upstream confirms no conflicting backend work
2. Maintainer approves architecture
3. Integration tests pass
