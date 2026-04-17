# Test Matrix and Acceptance Gates

## 1) Test categories

## A. Spec and registry tests

- [ ] `SPEC-001` Fetch cloud spec succeeds.
- [ ] `SPEC-002` Fetch storage spec succeeds.
- [ ] `SPEC-003` OpenAPI root fields validated.
- [ ] `SPEC-004` Cloud operation count equals 189.
- [ ] `SPEC-005` Storage operation count equals 32.
- [ ] `SPEC-006` Total operation count equals 221.
- [ ] `SPEC-007` Operation IDs are globally unique.
- [ ] `SPEC-008` Tag metadata is preserved.

## B. Schema resolution tests

- [ ] `SCH-001` Parameter `$ref` resolution works.
- [ ] `SCH-002` Request body `$ref` resolution works.
- [ ] `SCH-003` Nested object schema flattening works.
- [ ] `SCH-004` Required fields retained after normalization.
- [ ] `SCH-005` Unresolved refs fail with explicit error.

## C. Request builder tests

- [ ] `REQ-001` Path placeholders replaced correctly.
- [ ] `REQ-002` Missing path field fails fast.
- [ ] `REQ-003` Query scalar serialization correct.
- [ ] `REQ-004` Query array serialization uses repeated keys.
- [ ] `REQ-005` Boolean query serialization stable.
- [ ] `REQ-006` JSON body serialization stable.
- [ ] `REQ-007` Optional body omitted when absent.
- [ ] `REQ-008` Required body field validation catches omissions.

## D. HTTP transport tests

- [ ] `HTTP-001` Auth header attached.
- [ ] `HTTP-002` Timeout enforcement works.
- [ ] `HTTP-003` Retry triggers on 429.
- [ ] `HTTP-004` Retry triggers on selected 5xx.
- [ ] `HTTP-005` Retry does not trigger on 4xx non-throttle.
- [ ] `HTTP-006` Backoff cap respected.
- [ ] `HTTP-007` JSON parse fallback handles invalid JSON.

## E. Error mapping tests

- [ ] `ERR-001` Hetzner error payload parsed (`code/message/details`).
- [ ] `ERR-002` Unauthorized mapped with auth guidance.
- [ ] `ERR-003` Not found mapped with resource guidance.
- [ ] `ERR-004` Conflict mapped with retry guidance.
- [ ] `ERR-005` Rate limit mapped with retry_after/rate data.
- [ ] `ERR-006` Unknown transport error mapped to stable internal code.

## F. MCP server protocol tests

- [ ] `MCP-001` Server starts on stdio.
- [ ] `MCP-002` `list_tools` returns all 221 operation tools.
- [ ] `MCP-003` Tool schemas include expected required fields.
- [ ] `MCP-004` `call_tool` dispatch executes targeted operation.
- [ ] `MCP-005` Unknown tool fails with explicit error.
- [ ] `MCP-006` Stdout remains protocol-clean (no stray logs).

## G. Operation coverage tests

- [ ] `COV-001` Every registry operation appears in `list_tools`.
- [ ] `COV-002` Every tool call route exists.
- [ ] `COV-003` Every operation has at least one serialization test.
- [ ] `COV-004` Every operation has at least one success/error mapping test.

## H. Installer tests

- [ ] `INS-001` Install writes valid config for each supported client.
- [ ] `INS-002` Install is idempotent.
- [ ] `INS-003` Status reports expected server entries.
- [ ] `INS-004` Repair can recover malformed entries.
- [ ] `INS-005` Uninstall removes only targeted entries.

## 2) Manual smoke checks

- [ ] `SMK-001` Start server and list tools from MCP inspector.
- [ ] `SMK-002` Call representative GET operation from cloud.
- [ ] `SMK-003` Call representative POST action operation from cloud.
- [ ] `SMK-004` Call representative GET operation from storage.
- [ ] `SMK-005` Call representative POST action operation from storage.
- [ ] `SMK-006` Trigger expected auth failure and verify error format.

## 3) Mandatory quality commands

- [ ] `ruff check .`
- [ ] `mypy src/`
- [ ] `pytest -v`

## 4) Release acceptance gates

The build is releasable only when all are true:

- [ ] All tests above are green.
- [ ] All quality commands are green.
- [ ] 221 operations are implemented and exposed.
- [ ] README is complete and consistent with actual behavior.
- [ ] Installer flow verified on available local environment.
