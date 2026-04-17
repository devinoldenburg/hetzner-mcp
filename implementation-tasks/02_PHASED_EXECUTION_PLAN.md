# Phased Execution Plan (Detailed)

## Phase 0 - Repository and packaging baseline

Objective: create a clean, reproducible Python package foundation for MCP server work.

Tasks:

- [ ] Create project metadata in `pyproject.toml`.
- [ ] Define package name, Python version floor, dependencies, scripts.
- [ ] Add entry points for server, installer, and CLI utilities.
- [ ] Create `src/hetzner_mcp` package skeleton.
- [ ] Add initial `__init__.py` and `__main__.py` wiring.
- [ ] Add `.gitignore` and baseline dev tooling config.
- [ ] Add `README.md` placeholder sections to be filled later.

Validation:

- [ ] Package imports succeed locally.
- [ ] Console scripts resolve after editable install.

---

## Phase 1 - Spec ingestion and lock strategy

Objective: reliably ingest official Hetzner specs and make updates deterministic.

Tasks:

- [ ] Add script to fetch both official spec URLs.
- [ ] Store fetched specs in versioned local cache path.
- [ ] Save checksum/hash metadata for reproducibility.
- [ ] Add schema sanity checks (openapi version, servers, paths).
- [ ] Add operation counting report by API and tag.
- [ ] Add "spec drift" detection command.

Validation:

- [ ] Script produces stable artifact set from both URLs.
- [ ] Counts match expected 189 + 32 = 221.

---

## Phase 2 - Operation model normalization

Objective: convert raw OpenAPI operations into a normalized internal registry model.

Tasks:

- [ ] Define normalized operation entity with fields:
  - operation_id
  - api_domain (cloud or storage)
  - method
  - path
  - tags
  - summary/description
  - parameters (path/query/header if needed)
  - request body schema
  - response shape metadata
- [ ] Normalize request parameter schemas from refs.
- [ ] Flatten and resolve request body definitions.
- [ ] Capture required vs optional input metadata.
- [ ] Add strict uniqueness validation for operation IDs.
- [ ] Emit machine-readable registry artifact for runtime consumption.

Validation:

- [ ] Registry emits exactly 221 unique operations.
- [ ] No unresolved schema references remain.

---

## Phase 3 - Runtime configuration and auth

Objective: establish robust runtime config for API host + auth + transport settings.

Tasks:

- [ ] Define config model for tokens and endpoint base URLs.
- [ ] Support environment variables:
  - `HETZNER_TOKEN` (default)
  - optional per-product token overrides if needed
- [ ] Add validation for missing token conditions.
- [ ] Implement secure config loading and redaction helpers.
- [ ] Add timeout and retry configuration.
- [ ] Add user-agent composition strategy.

Validation:

- [ ] Missing token failure is clear and actionable.
- [ ] Token values never appear in logs/errors.

---

## Phase 4 - HTTP client and request builder

Objective: build resilient request execution layer independent of MCP transport.

Tasks:

- [ ] Build HTTP transport wrapper for JSON API requests.
- [ ] Add path parameter interpolation with strict required checks.
- [ ] Add query parameter serialization (including repeated arrays).
- [ ] Add JSON body encoder for application/json operations.
- [ ] Implement retry policy for `429` and selected `5xx` codes.
- [ ] Implement backoff with jitter and cap.
- [ ] Normalize non-2xx responses into structured error model.
- [ ] Capture rate-limit headers when present.

Validation:

- [ ] Happy-path requests work against mocks.
- [ ] Retry triggers on expected status codes.
- [ ] Serialization matches spec semantics.

---

## Phase 5 - MCP server core (dynamic tools)

Objective: expose operation registry as dynamic MCP tools.

Tasks:

- [ ] Implement low-level MCP server bootstrap.
- [ ] Implement `list_tools` dynamically from operation registry.
- [ ] Implement `call_tool` dispatch by operation ID.
- [ ] Map tool arguments to request builder inputs.
- [ ] Return structured MCP text content + structured payload.
- [ ] Ensure strict stdout discipline for JSON-RPC.
- [ ] Ensure server startup/health logs go to stderr only.

Validation:

- [ ] MCP inspector shows all operation tools.
- [ ] Tool calls route correctly by operation ID.

---

## Phase 6 - Helper tools for agents

Objective: improve discoverability and safer operation usage for AI agents.

Tasks:

- [ ] Add `list_api_operations` tool with filter options.
- [ ] Add `get_api_operation_details` tool with schema-focused output.
- [ ] Add `search_api_operations` tool (keywords/tags/path/method).
- [ ] Add optional `wait_for_action` helper for action polling workflows.
- [ ] Add response examples where available.

Validation:

- [ ] Agent can discover exact operation before invocation.
- [ ] Action workflows are usable without manual polling loops.

---

## Phase 7 - Installer and client configuration

Objective: one-command setup for common MCP clients.

Tasks:

- [ ] Implement `hetzner-mcp install` command.
- [ ] Auto-detect client config files for:
  - Claude Desktop
  - Claude Code
  - Cursor
  - Cline
  - Windsurf
  - OpenCode
- [ ] Apply or merge MCP config safely.
- [ ] Implement `status`, `diagnose`, `repair`, `uninstall`.
- [ ] Add clear restart guidance post-install.

Validation:

- [ ] Install writes valid config JSON/JSONC formats.
- [ ] Repair recovers from common broken states.

---

## Phase 8 - Comprehensive testing

Objective: prove full functional coverage and reliability.

Tasks:

- [ ] Add unit tests for parser/registry/model validation.
- [ ] Add unit tests for request builder edge cases.
- [ ] Add transport tests for retry/timeouts/error normalization.
- [ ] Add MCP protocol tests for list and call behavior.
- [ ] Add coverage test asserting all 221 operations are registered.
- [ ] Add golden tests for tool schema shape.
- [ ] Add optional live smoke test markers behind env guard.

Validation:

- [ ] All tests pass in local and CI.
- [ ] Coverage gates for critical modules pass.

---

## Phase 9 - Quality gates and CI

Objective: prevent regressions and enforce baseline quality.

Tasks:

- [ ] Add lint, type-check, and test jobs in CI.
- [ ] Add coverage report and failure threshold.
- [ ] Add pre-commit or equivalent checks.
- [ ] Add spec-sync validation in CI for drift awareness.

Validation:

- [ ] CI is green on clean branch.

---

## Phase 10 - README and docs polish

Objective: deliver polished docs in Aceternity MCP style.

Tasks:

- [ ] Build hero section with concise value proposition.
- [ ] Add install and quick start blocks.
- [ ] Add tools table and operation coverage summary.
- [ ] Add practical agent prompt examples.
- [ ] Add troubleshooting/security sections.
- [ ] Add development and release notes.

Validation:

- [ ] New user can install and call tools from docs only.

---

## Phase 11 - Final release checklist

Objective: close all program gates and publish-ready state.

Tasks:

- [ ] Verify 221/221 operation checklist completion.
- [ ] Verify install and server command entry points.
- [ ] Verify all tests and quality gates.
- [ ] Verify docs are accurate and current.
- [ ] Tag release candidate checklist as complete.

Validation:

- [ ] Program ready for release and end-user adoption.
