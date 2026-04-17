# Operation Implementation Playbook (Use for Every Operation)

This is the mandatory per-operation workflow. Repeat this for all 221 operations.

## Required per-operation lifecycle

For each operation ID in `05_OPERATION_CHECKLIST_ALL_221.md`, execute these steps:

1. [ ] Locate operation in normalized registry.
2. [ ] Confirm method + path + API domain match source spec.
3. [ ] Confirm tag/category mapping is correct.
4. [ ] Extract parameter definitions (path/query).
5. [ ] Extract request body schema (if present).
6. [ ] Identify required fields and nullable semantics.
7. [ ] Generate MCP input schema shape for this operation.
8. [ ] Add operation to dynamic `list_tools` output.
9. [ ] Verify deterministic tool name equals `operationId`.
10. [ ] Add dispatcher route in `call_tool` logic via registry lookup.
11. [ ] Implement argument splitting into path/query/body.
12. [ ] Validate missing required fields produce clear error.
13. [ ] Build URL path with encoded path variables.
14. [ ] Build query string with correct array handling.
15. [ ] Build JSON body (if request body required/optional).
16. [ ] Execute HTTP request with auth + timeout + retries.
17. [ ] Parse success response as JSON.
18. [ ] Parse error response and map into normalized error object.
19. [ ] Return MCP response with human-readable text + structured data.
20. [ ] Add unit test for input validation branch.
21. [ ] Add unit test for request serialization branch.
22. [ ] Add unit test for successful response mapping.
23. [ ] Add unit test for error response mapping.
24. [ ] Add integration-style mock test for end-to-end tool call.
25. [ ] Mark operation checklist item complete only after all tests pass.

## Additional requirements for action endpoints

Applies to operations typically returning async actions (many `POST .../actions/...` endpoints):

1. [ ] Confirm action response shape extraction.
2. [ ] Expose action identifiers in structured output.
3. [ ] Ensure helper `wait_for_action` can consume action ID.
4. [ ] Validate polling behavior for success/failure/timeout paths.

## Additional requirements for list endpoints

1. [ ] Validate pagination parameters (`page`, `per_page`) handling.
2. [ ] Preserve `meta.pagination` and related response metadata.
3. [ ] Ensure query filter pass-through is possible for supported params.

## Additional requirements for delete endpoints

1. [ ] Ensure idempotent behavior messaging is clear.
2. [ ] Handle `404 not_found` mapping with actionable guidance.

## Additional requirements for update/create endpoints

1. [ ] Validate request body required keys strictly.
2. [ ] Preserve user-provided optional fields without dropping unknown-but-valid keys.
3. [ ] Ensure schema-driven validation errors are explicit.

## Per-operation completion stamp template

Use this template in tracking notes while executing:

```
Operation: <operationId>
Method/Path: <METHOD /path>
API Domain: <cloud|storage>
Registry Added: yes/no
Tool Listed: yes/no
Call Dispatch: yes/no
Validation Tests: pass/fail
Serialization Tests: pass/fail
Success Mapping Tests: pass/fail
Error Mapping Tests: pass/fail
Integration Mock Test: pass/fail
Checklist Marked: yes/no
Commit SHA: <sha>
```

## Global strict rule

No operation entry may be checked as complete unless all operation lifecycle items above are done and test green.
