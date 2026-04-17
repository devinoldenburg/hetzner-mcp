# Component-by-Component Task Breakdown

This file breaks down implementation work at module level. Use it as the engineering execution checklist.

## A) Project structure tasks

- [ ] Create package directory tree under `src/hetzner_mcp`.
- [ ] Create module boundaries for:
  - config
  - spec_sync
  - schema_resolver
  - operation_registry
  - http_client
  - request_builder
  - error_model
  - mcp_server
  - installer
  - cli
  - diagnostics
- [ ] Define public API exports and internal/private boundaries.
- [ ] Add module-level docstrings with responsibilities.

## B) Config system tasks

- [ ] Define typed runtime config object.
- [ ] Add env resolution order and precedence rules.
- [ ] Add token presence validation.
- [ ] Add token masking/redaction helper.
- [ ] Add timeout + retry defaults and overrides.
- [ ] Add base URL override guards.

## C) Spec sync tasks

- [ ] Implement fetch of cloud and storage specs.
- [ ] Validate successful HTTP status and JSON parsing.
- [ ] Save fetched specs to local cache files.
- [ ] Save content hash and fetch timestamp metadata.
- [ ] Verify expected top-level OpenAPI structure.
- [ ] Add command output with counts by method and tag.

## D) Schema resolution tasks

- [ ] Resolve local `$ref` pointers in parameters.
- [ ] Resolve local `$ref` pointers in request bodies.
- [ ] Resolve local `$ref` pointers in response schemas.
- [ ] Detect unresolved refs and fail fast.
- [ ] Preserve `required` semantics.
- [ ] Normalize enum/default metadata for tool hints.

## E) Operation registry tasks

- [ ] Build normalized operation records from both specs.
- [ ] Ensure operation ID uniqueness globally.
- [ ] Preserve source tag/category and API domain.
- [ ] Attach input schema snapshots for MCP tool input.
- [ ] Attach response shape metadata for docs/introspection.
- [ ] Emit canonical JSON registry artifact.

## F) Request builder tasks

- [ ] Map operation arguments into path/query/body buckets.
- [ ] Validate required path params are present.
- [ ] Validate required body keys where schema indicates.
- [ ] Serialize query arrays as repeated keys.
- [ ] Serialize booleans and numerics correctly.
- [ ] Include `Content-Type: application/json` for body ops.
- [ ] Include `Authorization: Bearer <token>` header.

## G) HTTP transport tasks

- [ ] Implement request execution wrapper with timeout.
- [ ] Add transient retry policy for `429` and `5xx`.
- [ ] Add capped exponential backoff with jitter.
- [ ] Add safe max retry attempts default.
- [ ] Parse JSON responses and preserve raw fallback on parse error.
- [ ] Capture request ID and rate limit headers when present.

## H) Error normalization tasks

- [ ] Define structured error contract with fields:
  - status_code
  - hetzner_error_code
  - message
  - details
  - request_context
- [ ] Map standard Hetzner error payload shape (`error.code`, `error.message`, `error.details`).
- [ ] Map auth failures into user-actionable guidance.
- [ ] Map throttling failures into retry guidance.
- [ ] Map unknown transport failures into stable internal error code.

## I) MCP server tasks

- [ ] Initialize low-level MCP server.
- [ ] Implement dynamic `list_tools` from operation registry.
- [ ] Implement dynamic `call_tool` dispatch.
- [ ] Validate incoming argument object shape.
- [ ] Build request from operation metadata + args.
- [ ] Execute request and return structured content.
- [ ] Ensure no stdout contamination by logger output.

## J) Agent helper tools tasks

- [ ] Implement operation listing helper.
- [ ] Implement operation detail helper with parameter docs.
- [ ] Implement operation search helper by keyword/tag/path/method.
- [ ] Implement long-running action wait helper.
- [ ] Add consistent output formats across helper tools.

## K) Installer and config integration tasks

- [ ] Add auto-config writers for each client format.
- [ ] Add safe merge behavior (do not overwrite unrelated servers).
- [ ] Add idempotent install behavior.
- [ ] Add uninstall behavior that only removes this server entry.
- [ ] Add diagnostics command with client config check report.
- [ ] Add repair command to fix malformed/partial configs.

## L) Testing tasks (by module)

- [ ] Config tests for env precedence and validation.
- [ ] Spec sync tests for fetch failure and integrity checks.
- [ ] Resolver tests for nested refs and required fields.
- [ ] Registry tests for counts, uniqueness, and determinism.
- [ ] Request builder tests for path/query/body serialization.
- [ ] Transport tests for retry policy and timeout behavior.
- [ ] Error mapping tests for common Hetzner failures.
- [ ] MCP protocol tests for list and call lifecycle.
- [ ] Coverage tests for 221 registered operations.

## M) Documentation tasks

- [ ] Add architecture overview.
- [ ] Add setup and auth section.
- [ ] Add tool catalog and examples.
- [ ] Add troubleshooting matrix.
- [ ] Add contribution and local dev instructions.
