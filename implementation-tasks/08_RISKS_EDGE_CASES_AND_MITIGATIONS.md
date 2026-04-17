# Risks, Edge Cases, and Mitigations

## 1) API evolution risk

Risk:

- Hetzner may add/change/remove operations in upstream specs.

Mitigations:

- [ ] Add spec hash tracking.
- [ ] Add spec drift detection command.
- [ ] Add CI alert when operation count or IDs change.
- [ ] Regenerate registry deterministically from source specs.

## 2) Operation schema complexity risk

Risk:

- Complex nested schemas or refs can break input schema generation.

Mitigations:

- [ ] Implement robust `$ref` resolver.
- [ ] Add tests for nested object and array schemas.
- [ ] Fail fast with explicit unresolved-ref diagnostics.

## 3) Auth and secret leakage risk

Risk:

- Tokens accidentally logged in debug output or exceptions.

Mitigations:

- [ ] Redact all token-like values in logs.
- [ ] Log to stderr only with safe formatting.
- [ ] Add unit test asserting token redaction.

## 4) Rate-limiting and transient failure risk

Risk:

- Frequent `429` or intermittent `5xx` can cause flaky behavior.

Mitigations:

- [ ] Add retries with capped exponential backoff.
- [ ] Surface rate-limit headers in structured output.
- [ ] Add deterministic retry tests.

## 5) MCP protocol corruption risk

Risk:

- Logging to stdout can break stdio JSON-RPC sessions.

Mitigations:

- [ ] Explicit stdout/stderr policy.
- [ ] Startup check that logger uses stderr.
- [ ] Protocol test verifying clean stdout behavior.

## 6) Tool naming instability risk

Risk:

- Name changes break agent prompts/workflows.

Mitigations:

- [ ] Use operation IDs as canonical tool names.
- [ ] Add snapshot tests for tool name set.
- [ ] Add backward compatibility policy for renamed operations.

## 7) Request serialization mismatch risk

Risk:

- Query arrays/body shapes might not match API expectations.

Mitigations:

- [ ] Add serialization tests for all parameter types used.
- [ ] Add per-tag representative operation tests.
- [ ] Verify behavior against documented examples where available.

## 8) Installer misconfiguration risk

Risk:

- Auto-writing client configs may overwrite unrelated entries.

Mitigations:

- [ ] Merge, do not replace, existing config maps.
- [ ] Backup config before modifications when possible.
- [ ] Add uninstall logic scoped to server key only.

## 9) Large dynamic tool list usability risk

Risk:

- 221 tools may be difficult to navigate for agents.

Mitigations:

- [ ] Add helper tools for operation search/filter/detail.
- [ ] Tag operations by product and resource group.
- [ ] Provide strong README examples and prompt patterns.

## 10) False completion risk

Risk:

- Project marked complete before true full coverage.

Mitigations:

- [ ] Completion requires 221 checklist items checked.
- [ ] Completion requires coverage tests proving 221 tools listed.
- [ ] Completion requires all quality gates green.
