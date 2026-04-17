# Program Rules and Scope

## 1) Hard scope (v1)

- Products to support:
  - Hetzner Cloud API: `https://api.hetzner.cloud/v1`
  - Hetzner Storage API: `https://api.hetzner.com/v1`
- Source-of-truth specs:
  - `https://docs.hetzner.cloud/cloud.spec.json`
  - `https://docs.hetzner.cloud/hetzner.spec.json`
- Total operations to expose through MCP tools: **221**
  - Cloud: **189 operations**
  - Storage: **32 operations**

## 2) Out of scope (v1)

- DNS API (`dns.hetzner.com`) unless explicitly added in a future phase.
- Robot API and unrelated Hetzner services outside the two specs above.
- UI/web dashboard implementation.

## 3) Non-negotiable requirements

- Every operation in both specs must be callable from MCP.
- No manual endpoint omission.
- Strong structured error responses for API failures.
- Deterministic tool naming based on operation IDs.
- Agent-friendly tool discovery and operation introspection.
- Install UX for major MCP clients (Claude Desktop, Claude Code, Cursor, Cline, Windsurf, OpenCode).
- Comprehensive tests for registration coverage and request execution behavior.

## 4) Security requirements

- Auth via bearer token only (no token logging ever).
- Redact sensitive values from logs and diagnostics.
- Safe defaults: finite timeouts, bounded retries, explicit user-agent.
- No secret persistence in repository.
- Environment-based configuration for tokens.

## 5) Operational requirements

- Support stdio MCP transport.
- Ensure stdout is reserved for JSON-RPC frames only.
- Route all diagnostics/logging to stderr.
- Handle API throttling (`429`) with backoff.
- Provide stable failure messages for common Hetzner API error modes.

## 6) Documentation requirements

- README style should mirror Aceternity MCP style:
  - Hero section
  - Badges
  - Fast install
  - Tool table
  - Example prompts
  - Client setup section
  - Troubleshooting and security notes
- Include clear setup for `HETZNER_TOKEN` and optional product-specific tokens.

## 7) Definition of done

All items below must be true simultaneously:

- [ ] 221/221 operations are generated and exposed as MCP tools.
- [ ] Tool names are stable and deterministic across runs.
- [ ] Request building works for path/query/body parameters from both specs.
- [ ] API errors are normalized and surfaced in structured MCP output.
- [ ] Retry behavior for transient failures is tested.
- [ ] Install/repair/status/diagnose flows work for supported clients.
- [ ] Unit + integration tests pass.
- [ ] Quality checks (`ruff`, `mypy`, `pytest`) pass.
- [ ] README is fully updated in the desired style.
