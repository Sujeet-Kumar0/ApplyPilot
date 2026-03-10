"""Compatibility shim for dev-branch backend imports.

The canonical backend implementation lives in applypilot.apply.agent_backends.
This module re-exports that surface so merged code and tests keep working
without maintaining two competing backend layers.
"""

from applypilot.apply.agent_backends import (
    AgentBackend,
    AgentBackendError,
    BACKENDS,
    BackendError,
    ClaudeBackend,
    CodexBackend,
    DEFAULT_BACKEND,
    InvalidBackendError,
    OpenCodeBackend,
    VALID_BACKENDS,
    build_claude_command,
    build_codex_command,
    build_manual_command,
    detect_backends,
    extract_result_status,
    get_available_backends,
    get_backend,
    get_preferred_backend,
    resolve_backend_name,
    resolve_default_agent,
    resolve_default_model,
)

__all__ = [
    "AgentBackend",
    "AgentBackendError",
    "BACKENDS",
    "BackendError",
    "ClaudeBackend",
    "CodexBackend",
    "DEFAULT_BACKEND",
    "InvalidBackendError",
    "OpenCodeBackend",
    "VALID_BACKENDS",
    "build_claude_command",
    "build_codex_command",
    "build_manual_command",
    "detect_backends",
    "extract_result_status",
    "get_available_backends",
    "get_backend",
    "get_preferred_backend",
    "resolve_backend_name",
    "resolve_default_agent",
    "resolve_default_model",
]
