# 9router Integration and Migration Guide

Purpose: provide operational, vendor-agnostic guidance for integrating an OpenAI-compatible gateway ("9router" style) with ApplyPilot. Covers base URL patterns, endpoint setup, model mapping, key hygiene, canary rollout, observability, rollback, and stepwise migration instructions. All examples use placeholders for secrets.

## Base URL Patterns

- Use a single base URL environment variable such as LLM_URL that points at the gateway root exposing an OpenAI-compatible v1 API surface.
- Canonical examples (placeholders):
  - https://my-gateway.example.com/v1
  - https://9router.local:8443/v1
- The client configuration must append the API path used by the runtime, for example: `${LLM_URL}/chat/completions` or `${LLM_URL}/responses` depending on gateway routing. Keep the base URL stable across rollout phases.

## Endpoint Setup

1. Configure runtime environment variables (example placeholders):

```bash
export LLM_URL="https://my-9router.example.com/v1"
export LLM_API_KEY="sk-xxxxxxxx"
export LLM_MODEL="gpt-4o-mini"
```

2. Validate reachability:
- Run a lightweight health probe against the base URL (no secrets in logs). Example HTTP GET to `${LLM_URL}/health` or a minimal `GET ${LLM_URL}/v1/models` if supported.
- Fail-open policy: do not leak keys in health logs. Use masked output and record only HTTP status codes and latency.

3. Register the gateway where required by the orchestration backend (opencode example):

```text
opencode mcp add my-mcp --provider=openai --url "$LLM_URL" --api-key "$LLM_API_KEY" --model "$LLM_MODEL"
```

Notes:
- Use the orchestration tool's registration mechanism rather than embedding gateway logic in application code.
- Keep registration idempotent and automatable; store registration metadata outside of git.

## Model Mapping

- Maintain a mapping between logical model names used by ApplyPilot and gateway-exposed model identifiers. Keep this map in configuration, not code.
- Example mapping structure (YAML/JSON):

```yaml
llm:
  default_model: "gpt-4o-mini"
  mappings:
    text-generation: "gpt-4o-mini"
    chat: "gpt-4o-chat"
    embedding: "embed-1"
```

Operational guidance:
- Prefer stable model aliases in config (logical names) and point them to gateway model names per-environment.
- During canary rollouts, change the mapping for a logical name in staging first, then prod.

## Key Hygiene

- Never commit API keys, tokens, or credentials to source control. Use placeholders in examples.
- Recommended storage: environment variables in runner, secret manager (Vault, cloud secrets), or CI secrets.
- Rotation: rotate gateway keys on a regular schedule and validate by probing an ephemeral endpoint after rotation.
- Least privilege: create per-environment keys (staging, prod) and restrict scopes when gateway supports scopes.
- Auditing: ensure gateway audit logs are available and retained per your compliance needs; record only the minimal metadata in application logs (request id, status, latency).

Practical checklist:
- .gitignore local .env files
- Use CI secrets for workflow_dispatch variables
- Do not echo secrets in CI logs; mask them in action outputs

## Canary Rollout

Goals: validate model and gateway behavior under production-like traffic with minimal blast radius.

Steps:
1. Prepare canary environment or tag (e.g., APPLY_CANARY=true or separate service instances).
2. Update model mapping to point logical alias to canary model for a small percentage of traffic or a subset of users.
3. Route a small fraction of requests (1-5%) to canary using one of:
   - Gateway-level routing rules (preferred)
   - Client-side header (e.g., X-Canary:true) and client logic
   - Load balancer rules that select canary instances
4. Monitor key metrics (latency, error rate, token usage, hallucination indicators) and compare to baseline.
5. Gradually increase traffic to canary while monitoring.
6. If metrics remain acceptable, promote mapping to larger percentage or full rollout.

Decision criteria (examples):
- Error rate increase < 0.5% absolute
- Latency increase < 20% relative
- No regression on functional tests that use the model's output programmatically

## Observability

Instrument these signals at minimum:
- Request success/error counts (4xx, 5xx)
- Per-model and per-alias latency p50/p95/p99
- Token consumption and cost per request
- End-to-end request traces (correlate application request id with gateway request id)
- Quality signals where possible (automatic semantic checks, automated smoke tests, human-in-the-loop feedback)

Practical tips:
- Add a request id to every LLM call; persist it in gateway logs for correlation.
- Emit metrics to your metrics backend; tag by environment, model_alias, and canary flag.
- Keep a weekly snapshot of cost and token usage to detect regressions early.

## Rollback

Plan for rapid rollback with minimal data loss.

Rollback approaches:
- Revert model mapping to previous alias in config and redeploy mapping change.
- If mapping cannot be changed atomically, revert at gateway registration (disable canary model) or update routing rules to send all traffic back to stable model.

Verification after rollback:
1. Smoke test: run a scripted set of representative requests and verify expected responses or status codes.
2. Monitor metrics for return to baseline (error rate, latency, token usage).

Notes:
- Keep the previous model identifier and mapping around for at least one full audit cycle to support post-mortem analysis.
- Document the rollback runbook in the same repo so operators can follow steps without needing tribal knowledge.

## Migration Steps

1. Readiness
   - Inventory models and logical aliases
   - Confirm secret storage and CI secret entries
   - Prepare automated health probes and smoke tests

2. Staging validation
   - Point staging mapping to gateway model
   - Run full integration test suite against staging mapping
   - Validate observability pipelines ingest gateway request ids and metrics

3. Canary
   - Start canary per Canary Rollout section
   - Run canary for a minimum verification window (e.g., 24 hours or X requests)

4. Gradual promotion
   - Increase traffic per decision criteria
   - Continue observability checks

5. Full promotion
   - Update prod mapping to point to new model
   - Run smoke tests

6. Post-migration
   - Retain previous mapping for rollback for a retention window
   - Capture post-migration runbook entry with observed metrics

## Operational Verification Checklist

- [ ] LLM_URL, LLM_API_KEY, LLM_MODEL present in environment (use CI secrets in workflow)
- [ ] Health probe passes (status 200) for gateway base URL
- [ ] Mapping file contains logical aliases and points to expected gateway models
- [ ] Canary configured and receiving small fraction of traffic
- [ ] Observability tags present: request_id, model_alias, env
- [ ] Rollback procedure documented and smoke tests available

## Frequently Asked Operational Questions

Q: How should I test without exposing real keys? A: Use staging keys and masked logs. Use dummy keys in developer environments.

Q: What if the gateway uses a different API shape? A: Add a lightweight adapter layer in deployment infra that normalizes the gateway to OpenAI-compatible v1 shape. Keep that adapter outside of application code.

----

Appendix: links to canonical design patterns (vendor-agnostic):
- Minimal health check pattern
- Canary rollout checklist
- Key rotation checklist
