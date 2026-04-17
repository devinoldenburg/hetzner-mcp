# Granular Commit Plan (Small Local Commits)

Use this as the local commit sequence. Keep each commit narrowly scoped.

## Phase 0 commits

1. [ ] `chore: initialize project metadata and packaging skeleton`
2. [ ] `chore: add base src package and entrypoint stubs`
3. [ ] `chore: add lint, type-check, and test configuration`

## Phase 1 commits

4. [ ] `feat: add cloud and storage spec fetch command`
5. [ ] `feat: add local spec cache and checksum metadata`
6. [ ] `feat: add spec sanity validation and count reporting`

## Phase 2 commits

7. [ ] `feat: add normalized operation model definitions`
8. [ ] `feat: add schema reference resolver for parameters`
9. [ ] `feat: add schema reference resolver for request bodies`
10. [ ] `feat: add operation registry builder for cloud spec`
11. [ ] `feat: add operation registry builder for storage spec`
12. [ ] `test: assert global operation id uniqueness`
13. [ ] `test: assert registry count equals 221`

## Phase 3 commits

14. [ ] `feat: add runtime config model and env loading`
15. [ ] `feat: add token validation and redaction helpers`
16. [ ] `test: cover config precedence and missing token errors`

## Phase 4 commits

17. [ ] `feat: add request path interpolation module`
18. [ ] `feat: add query parameter serializer`
19. [ ] `feat: add request body serializer`
20. [ ] `test: add request builder edge case coverage`
21. [ ] `feat: add http transport wrapper with timeout`
22. [ ] `feat: add retry policy for 429 and 5xx responses`
23. [ ] `feat: add structured hetzner error normalization`
24. [ ] `test: add transport retry and error mapping tests`

## Phase 5 commits

25. [ ] `feat: add low-level mcp server bootstrap`
26. [ ] `feat: implement dynamic list_tools from registry`
27. [ ] `feat: implement dynamic call_tool dispatch`
28. [ ] `test: add mcp list_tools and call_tool protocol tests`
29. [ ] `fix: enforce stderr-only logging for stdio protocol safety`

## Phase 6 commits

30. [ ] `feat: add list_api_operations helper tool`
31. [ ] `feat: add get_api_operation_details helper tool`
32. [ ] `feat: add search_api_operations helper tool`
33. [ ] `feat: add wait_for_action helper tool`
34. [ ] `test: add helper tool output contract tests`

## Phase 7 commits

35. [ ] `feat: add installer command scaffolding`
36. [ ] `feat: add claude desktop config integration`
37. [ ] `feat: add claude code config integration`
38. [ ] `feat: add cursor config integration`
39. [ ] `feat: add cline config integration`
40. [ ] `feat: add windsurf config integration`
41. [ ] `feat: add opencode config integration`
42. [ ] `feat: add status command`
43. [ ] `feat: add diagnose command`
44. [ ] `feat: add repair command`
45. [ ] `feat: add uninstall command`
46. [ ] `test: add installer idempotency and repair tests`

## Phase 8 commits

47. [ ] `test: add per-operation registry parity tests`
48. [ ] `test: add representative cloud operation call matrix`
49. [ ] `test: add representative storage operation call matrix`
50. [ ] `test: add action endpoint polling workflow tests`

## Phase 9 commits

51. [ ] `ci: add lint, type-check, and test workflow`
52. [ ] `ci: add coverage gate and report`
53. [ ] `ci: add spec drift check`

## Phase 10 commits

54. [ ] `docs: add complete README hero and install sections`
55. [ ] `docs: add full tools matrix and examples`
56. [ ] `docs: add client config and troubleshooting`
57. [ ] `docs: add security and development sections`

## Phase 11 commits

58. [ ] `chore: final acceptance checklist and release notes`

## Optional micro-commit expansion rule

If any commit above exceeds about 200 changed lines or mixes concerns, split it further before committing.
