"""Native Playwright agent — uses Bedrock LLM + Playwright MCP directly.

Replaces Codex/Claude/OpenCode CLI for auto-apply. No external CLI needed,
no usage limits. Uses the mcp Python library for MCP protocol communication
with the Playwright MCP server.

Design: "Don't teach the model to be smart — make it impossible to be wrong."
The agent loop enforces correctness mechanically:
  1. _is_evaluate_write() blocks any browser_evaluate that tries to set values
  2. Auto-snapshot on "Ref not found" — model never sees the error
  3. _extract_field_map() injects a clean label→ref table after every snapshot
The system prompt is deterministic: zero prose, only patterns to copy and IF→THEN rules.

SRP: Only runs the agent loop. Does not manage Chrome (chrome.py),
does not build prompts (native_prompt.py), does not parse results.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
import subprocess
import sys
import time
from typing import Any

from applypilot.apply.backends import (
    AutoApplyBackend,
    BackendExecution,
    ProcessRegistrar,
    ProcessUnregister,
    extract_result_status,
)

log = logging.getLogger(__name__)

_MAX_ITERATIONS = 35
_MAX_CONSECUTIVE_ERRORS = 3
_MAX_REPEATED_CALLS = 2

# ── Evaluate write detection ─────────────────────────────────────────────
# Patterns that indicate browser_evaluate is trying to WRITE to the page.
# React/Angular/Vue ignore raw JS .value= assignments — the form submits
# with empty fields. This was the root cause of all Cloudflare failures.
_EVALUATE_WRITE_PATTERNS = (
    ".value=",
    ".value =",
    ".value=",
    ".checked=",
    ".checked =",
    ".click()",
    ".submit()",
    ".focus()",
    "innerHTML",
    "outerHTML",
    "setAttribute",
    "dispatchEvent",
    "removeChild",
    "appendChild",
)


def _is_evaluate_write(fn_body: str) -> bool:
    """True if a browser_evaluate function body attempts to modify the page."""
    return any(p in fn_body for p in _EVALUATE_WRITE_PATTERNS)


# ── Field map extraction ─────────────────────────────────────────────────
# After every browser_snapshot, parse the accessibility tree YAML and inject
# a clean label→ref lookup table. This eliminates the need for the LLM to
# call browser_evaluate to discover fields — the #1 source of wrong-ref bugs.
_FIELD_RE = _re.compile(r'(textbox|combobox|listbox|checkbox|radio|button|link)\s+"([^"]+)"\s+\[ref=(e\d+)\]')


def _extract_field_map(snapshot_text: str) -> str:
    """Parse snapshot and return a structured field→ref mapping."""
    fields = []
    for m in _FIELD_RE.finditer(snapshot_text):
        role, label, ref = m.groups()
        hint = ""
        if role == "combobox":
            hint = " (custom dropdown: click→type value→snapshot→click option)"
        elif role == "listbox":
            hint = " (real dropdown: use browser_select_option)"
        elif role in ("checkbox", "radio"):
            hint = " (use browser_click)"
        fields.append(f"  {label} | ref={ref} | {role}{hint}")
    if not fields:
        return ""
    return "\n\nFIELD MAP (use these refs with browser_type or browser_click):\n" + "\n".join(fields)


# ── System prompt ────────────────────────────────────────────────────────
# Zero prose. Every line is a pattern to copy or an IF→THEN rule.
# ~420 words. Works identically on any model because there's nothing to interpret.
_SYSTEM_PROMPT = """\
You are a browser automation agent. You fill job application forms.

## OUTPUT FORMAT
Every response: exactly one JSON tool call.
{"tool": "TOOL_NAME", "args": {ARGS}}

When done, output exactly one of:
RESULT:APPLIED
RESULT:FAILED:<reason>
RESULT:NEEDS_HUMAN:<reason>

No other text. No explanation. No planning. Just the tool call or the result.

## REFS
Refs come from browser_snapshot. They look like: e42, e88, e120.
Refs are NOT HTML ids. "first_name" is an HTML id — WRONG. "e88" is a ref — CORRECT.
If a ref fails → you will receive a fresh snapshot with correct refs automatically.

## TOOL PATTERNS

Fill a text field:
  SNAPSHOT: textbox "First Name" [ref=e88]
  CALL: {"tool":"browser_type","args":{"element":"First Name","ref":"e88","text":"John"}}

Click a button/checkbox/link:
  SNAPSHOT: button "Apply" [ref=e19]
  CALL: {"tool":"browser_click","args":{"element":"Apply","ref":"e19"}}

Real dropdown (snapshot shows listbox with options):
  CALL: {"tool":"browser_select_option","args":{"element":"Country","ref":"e20","values":["India"]}}

Custom dropdown (snapshot shows combobox, no options listed):
  1. {"tool":"browser_click","args":{"element":"Country","ref":"e95"}}
  2. {"tool":"browser_type","args":{"element":"Country search","ref":"e95","text":"India"}}
  3. {"tool":"browser_snapshot","args":{}}
  4. Click the matching option from the new snapshot

Upload a file:
  1. {"tool":"browser_click","args":{"element":"Upload resume","ref":"e30"}}
  2. {"tool":"browser_file_upload","args":{"paths":["/path/to/file.pdf"]}}

Switch tabs:
  {"tool":"browser_tabs","args":{"action":"list"}}
  {"tool":"browser_tabs","args":{"action":"select","index":1}}

## WORKFLOW
1. browser_navigate to the job URL
2. browser_snapshot
3. FIRST: dismiss any cookie consent/GDPR banner — click "Accept", "Accept All", "Accept Cookies", "OK", or "I agree". If none visible, continue.
4. Click Apply button using ref from snapshot
5. browser_snapshot — check what appeared:
   a. "How would you like to apply?" → click "Upload resume" or "Apply manually". NEVER "Import from LinkedIn/Indeed".
   b. Login/Register/Create Account page, OR fields named "Password"/"Verify Password" → STOP. Report RESULT:NEEDS_HUMAN:login_required
   c. Application form with FIELD MAP → continue to step 6.
6. For each field in the FIELD MAP:
   - textbox → browser_type with value from APPLICANT PROFILE
   - combobox → click, type value, snapshot, click option
   - checkbox → browser_click
7. Upload resume: browser_click upload button, then browser_file_upload
8. browser_snapshot to verify all fields filled
9. Click Submit button
10. browser_snapshot to confirm
11. If success text → RESULT:APPLIED. If more fields → go to step 6. If errors → fix and retry.

## RULES
R1. NEVER use browser_evaluate to set form values. It will be blocked.
R2. browser_evaluate is ONLY for reading text or checking errors.
R3. After EVERY click or navigate → browser_snapshot before doing anything else.
R4. If you see form fields → fill them. Do NOT look for login/auth.
R5. If stuck after 3 attempts → RESULT:NEEDS_HUMAN:<reason>.
R6. Login wall or CAPTCHA → RESULT:NEEDS_HUMAN:<reason>.
R7. Job closed or page broken → RESULT:FAILED:<reason>.
R8. After filling 3-5 fields → browser_snapshot to refresh refs.
"""


class NativePlaywrightBackend(AutoApplyBackend):
    """In-process agent using Bedrock LLM + Playwright MCP tools."""

    key = "native"
    label = "Native Playwright Agent"

    def __init__(self) -> None:
        self._active_procs: dict[int, subprocess.Popen] = {}

    @classmethod
    def is_installed(cls) -> bool:
        return True

    @classmethod
    def get_version(cls) -> str | None:
        return "native-2.0"

    def build_command(self, *, worker_dir, worker_id, port, model) -> list[str]:
        return ["native-playwright-agent"]

    def run(
            self,
            *,
            job: dict,
            port: int,
            worker_id: int,
            prompt: str,
            model: str | None,
            register_process: ProcessRegistrar,
            unregister_process: ProcessUnregister,
    ) -> BackendExecution:
        t0 = time.time()
        log.info("[native] Starting: %s @ %s", job.get("title", "?")[:50], job.get("site", "?"))

        from applypilot.apply.backends import job_log_path, log_header

        job_log = job_log_path(self.key, worker_id, job)
        log_lines: list[str] = [log_header(job, self.label)]

        try:
            output = asyncio.run(_run_agent(prompt, port, model, log_lines))
        except Exception as e:
            log.error("[native] Agent error: %s", e)
            output = f"RESULT:FAILED:{str(e)[:80]}"
            log_lines.append(f"\nERROR: {e}\n")

        log_lines.append(f"\n{'=' * 60}\nFINAL OUTPUT:\n{output}\n")
        # Redact sensitive fields from agent log before writing
        from applypilot.logging_config import redact_pii
        import re

        redacted = "\n".join(log_lines)
        redacted = re.sub(r'"text"\s*:\s*"[^"]*"(?=.*[Pp]assword)', '"text": "<redacted>"', redacted)
        # Also redact password values in tool calls (Password field fills)
        redacted = re.sub(r'(Password[^"]*"[^"]*"text"\s*:\s*)"[^"]*"', r'\1"<redacted>"', redacted)
        redacted = re.sub(r'\.fill\([\'"][^\'"]*[\'"]\)', '.fill(\'<redacted>\')', redacted)
        redacted = redact_pii(redacted)
        job_log.write_text(redacted, encoding="utf-8")
        log.debug("[native] Log: %s", job_log)

        elapsed_ms = int((time.time() - t0) * 1000)
        result_code = extract_result_status(output) or ""

        # Alert operator when the agent is stuck and needs human help.
        if "needs_human" in result_code.lower():
            _alert_human(job, result_code)

            # Login required: pause with Chrome open so user can sign in
            if "login" in result_code.lower():
                try:
                    console_msg = (
                        f"\n⏸️  Chrome is open on port {port}. Sign in manually, then press Enter to resume..."
                    )
                    sys.stderr.write(console_msg + "\n")
                    sys.stderr.flush()
                    input()  # Block until user presses Enter

                    # Retry after login
                    log.info("[native] Resuming after manual login...")
                    log_lines.append("\n--- RESUMED AFTER MANUAL LOGIN ---\n")
                    try:
                        output = asyncio.run(_run_agent(prompt, port, model, log_lines))
                        result_code = extract_result_status(output) or ""
                        elapsed_ms = int((time.time() - t0) * 1000)
                    except Exception as e:
                        log.error("[native] Resume failed: %s", e)
                        output = f"RESULT:FAILED:{str(e)[:80]}"
                except EOFError:
                    pass  # Non-interactive — can't pause

        return BackendExecution(
            raw_output=output,
            final_output=output,
            returncode=0 if "applied" in result_code.lower() else 1,
            duration_ms=elapsed_ms,
            skipped=False,
        )


def _alert_human(job: dict, reason: str) -> None:
    """Terminal bell + log warning when a job needs manual intervention.
    In headless mode, just log — no bell, no blocking.
    """
    from applypilot.config.execution_mode import is_headless

    title = job.get("title", "Unknown")[:50]
    site = job.get("site", "?")
    msg = f"⚠️  HUMAN NEEDED: {title} @ {site} — {reason}"
    log.warning(msg)
    if not is_headless():
        sys.stderr.write(f"\a\n{msg}\n")
        sys.stderr.flush()


async def _run_agent(prompt: str, port: int, model: str | None, log_lines: list[str]) -> str:
    """Run the agent loop inside an MCP session with Playwright tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server = StdioServerParameters(
        command="npx",
        args=[
            "@playwright/mcp@latest",
            f"--cdp-endpoint=http://localhost:{port}",
            "--viewport-size=1280x900",
            "--allow-unrestricted-file-access",
            # CRITICAL: Default incremental mode omits "unchanged" elements,
            # which hides form fields after the first snapshot. Full mode
            # returns the complete accessibility tree every time so the
            # field map extraction always sees all labels and refs.
            "--snapshot-mode=full",
        ],
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tool_map = {t.name: t for t in tools_result.tools}
            log_lines.append(f"MCP: {len(tools_result.tools)} tools available\n")

            return await _agent_loop(session, tool_map, prompt, model, log_lines)


async def _agent_loop(
        session: Any,
        tool_map: dict,
        prompt: str,
        model: str | None,
        log_lines: list[str],
) -> str:
    """Core loop with mechanical enforcement.

    Three enforcement layers prevent the LLM from deviating:
    1. _is_evaluate_write() blocks browser_evaluate that tries to set values
    2. Auto-snapshot on "Ref not found" — model gets fresh refs, never sees error
    3. _extract_field_map() injects label→ref table after every snapshot
    """
    from dataclasses import replace as _dc_replace
    from applypilot.llm import get_client, resolve_llm_config, LLMClient
    import time as _time

    # FIX: Honour AUTO_APPLY_MODEL from .env. Without this, the native agent
    # always used the default scoring model (Qwen) instead of the configured
    # apply model (Sonnet).
    if model:
        client = LLMClient(_dc_replace(resolve_llm_config(), model=model))
    else:
        client = get_client(tier="cheap")

    messages: list[dict[str, str]] = [
        {"role": "user", "content": prompt},
    ]

    consecutive_errors = 0
    full_output: list[str] = []
    last_call_key: str = ""
    repeat_count: int = 0

    for iteration in range(_MAX_ITERATIONS):
        t0 = _time.time()
        log.debug("[native] Iteration %d/%d", iteration + 1, _MAX_ITERATIONS)

        try:
            response = client.chat(
                [{"role": "system", "content": _SYSTEM_PROMPT}] + messages,
                max_output_tokens=1000,  # One tool call, not essays
            )
        except Exception as e:
            log.error("[native] LLM error: %s", e)
            log_lines.append(f"[iter {iteration + 1}] LLM ERROR: {e}")
            consecutive_errors += 1
            if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                return "RESULT:FAILED:llm_error"
            continue

        elapsed = _time.time() - t0
        consecutive_errors = 0
        full_output.append(response)
        messages.append({"role": "assistant", "content": response})
        log_lines.append(f"\n[iter {iteration + 1}] LLM ({elapsed:.1f}s):\n{response[:500]}")

        tool_call = _parse_tool_call(response)

        if not tool_call:
            result = extract_result_status(response)
            if result:
                log.info("[native] Result: %s (iteration %d)", result, iteration + 1)
                log_lines.append(f"\n[RESULT] {result}")
                return "\n".join(full_output)
            messages.append(
                {"role": "user", "content": "Respond with a tool call JSON or a RESULT: code. Nothing else."}
            )
            continue

        tool_name = tool_call["tool"]
        tool_args = tool_call.get("args", {})

        # ── ENFORCEMENT 1: Block browser_evaluate writes ──────────────
        # React/Angular/Vue ignore raw JS .value= assignments. The form
        # submits with empty fields despite visually showing values.
        # Hard-block so the model is forced to use browser_type instead.
        if tool_name == "browser_evaluate":
            fn = tool_args.get("function", "")
            if _is_evaluate_write(fn):
                msg = (
                    "BLOCKED: browser_evaluate cannot modify the page. "
                    "Use browser_type for text fields, browser_click for buttons/checkboxes. "
                    "Call browser_snapshot to get refs."
                )
                messages.append({"role": "user", "content": msg})
                log_lines.append(f"[iter {iteration + 1}] BLOCKED evaluate write")
                continue

        # ── ENFORCEMENT 2: Stuck detection ────────────────────────────
        # Same tool+args repeated = agent is stuck (e.g. browser_tabs with
        # wrong param 10x in a row on the Affirm run).
        call_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
        if call_key == last_call_key:
            repeat_count += 1
        else:
            last_call_key = call_key
            repeat_count = 1

        if repeat_count >= _MAX_REPEATED_CALLS:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"STUCK: {tool_name} called {repeat_count}x with same args. "
                        "Try a completely different approach or output RESULT:NEEDS_HUMAN:stuck"
                    ),
                }
            )
            log_lines.append(f"[iter {iteration + 1}] STUCK: {tool_name} x{repeat_count}")
            last_call_key = ""
            repeat_count = 0
            continue

        if tool_name not in tool_map:
            messages.append(
                {
                    "role": "user",
                    "content": (f"Unknown tool '{tool_name}'. Available: {', '.join(sorted(tool_map.keys()))}"),
                }
            )
            continue

        # ── Execute tool via MCP ──────────────────────────────────────
        try:
            t0 = _time.time()
            log.debug("[native] Calling %s(%s)", tool_name, json.dumps(tool_args)[:100])
            result = await session.call_tool(tool_name, tool_args)
            tool_elapsed = _time.time() - t0
            tool_output = ""
            for content in result.content:
                if hasattr(content, "text"):
                    tool_output += content.text
            tool_output = tool_output[:8000]
            log.debug("[native] Tool result (%0.1fs): %s", tool_elapsed, tool_output[:200])
            log_lines.append(
                f"[iter {iteration + 1}] TOOL {tool_name}({json.dumps(tool_args)[:80]}) "
                f"→ {tool_elapsed:.1f}s\n{tool_output[:500]}"
            )
        except Exception as e:
            tool_output = f"Tool error: {e}"
            log.warning("[native] Tool %s failed: %s", tool_name, e)
            log_lines.append(f"[iter {iteration + 1}] TOOL {tool_name} ERROR: {e}")

        # ── ENFORCEMENT 3: Auto-snapshot on ref-not-found ─────────────
        # When browser_type(ref="first_name") fails because the agent used
        # an HTML id instead of a snapshot ref, automatically take a fresh
        # snapshot and inject it with the field map. The model never sees
        # the error — it sees correct refs and can retry immediately.
        if "not found" in tool_output.lower() and "ref" in tool_output.lower():
            log_lines.append(f"[iter {iteration + 1}] AUTO-RECOVERY: ref not found → auto-snapshot")
            try:
                snap_result = await session.call_tool("browser_snapshot", {})
                snap_text = ""
                for c in snap_result.content:
                    if hasattr(c, "text"):
                        snap_text += c.text
                snap_text = snap_text[:8000]
                field_map = _extract_field_map(snap_text)
                tool_output = (
                    f"Ref not found. Here is a fresh snapshot with correct refs:\n"
                    f"{snap_text}{field_map}\n"
                    f"Use refs from THIS snapshot (e.g. e88). Never use HTML ids."
                )
                log_lines.append(f"[iter {iteration + 1}] AUTO-SNAPSHOT injected with {field_map.count('ref=')} fields")
            except Exception as e:
                log_lines.append(f"[iter {iteration + 1}] AUTO-SNAPSHOT failed: {e}")

        # ── ENFORCEMENT 4: Inject field map after snapshots ───────────
        # Gives the LLM a clean label→ref lookup table so it doesn't need
        # to call browser_evaluate to discover fields.
        elif tool_name == "browser_snapshot":
            field_map = _extract_field_map(tool_output)
            if field_map:
                tool_output += field_map

        messages.append({"role": "user", "content": f"Tool result:\n{tool_output}"})
        full_output.append(f"[{tool_name}] {tool_output[:300]}")

        # ── ENFORCEMENT: Detect login/signup pages programmatically ──
        _AUTH_PAGES = ("sign up", "sign in", "login", "log in", "create account", "register", "cold-join", "signup")
        output_lower = tool_output.lower()
        if any(p in output_lower for p in _AUTH_PAGES):
            log.info("[native] Auth page detected — stopping")
            log_lines.append("\n[ENFORCEMENT] Auth page detected in tool output — stopping")
            return "RESULT:NEEDS_HUMAN:login_required"

    log_lines.append(f"\n[RESULT] max_iterations ({_MAX_ITERATIONS})")
    return "RESULT:NEEDS_HUMAN:max_iterations_reached"


def _parse_tool_call(response: str) -> dict | None:
    """Extract the FIRST tool call from LLM response.

    The LLM often outputs multiple tool calls in one response.
    We execute only the first one, then loop back for the next.
    """
    # Find {"tool": "name", "args": {...}} — handle nested braces
    for match in _re.finditer(r'\{"tool"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*', response):
        start = match.end()
        depth = 0
        for i in range(start, len(response)):
            if response[i] == "{":
                depth += 1
            elif response[i] == "}":
                if depth == 0:
                    try:
                        obj = json.loads(match.group(0) + response[start: i + 1])
                        return obj
                    except json.JSONDecodeError:
                        break
                depth -= 1
        return {"tool": match.group(1), "args": {}}

    # Fallback: {"name": "browser_*", "arguments": {...}}
    for match in _re.finditer(r'\{"name"\s*:\s*"(browser_\w+)"', response):
        try:
            start = response.rfind("{", 0, match.start() + 1)
            end = response.find("}", match.end())
            if end > 0:
                obj = json.loads(response[start: end + 1])
                return {"tool": obj.get("name"), "args": obj.get("arguments", obj.get("args", {}))}
        except (json.JSONDecodeError, ValueError):
            return {"tool": match.group(1), "args": {}}

    return None
