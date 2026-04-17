# Hetzner MCP Implementation Task Folder

This folder is the full execution blueprint for building a complete `hetzner-mcp` server with full Cloud + Storage API coverage.

It contains planning only (no implementation code) and is meant to be executed step-by-step.

## Files in this folder

- `implementation-tasks/01_PROGRAM_RULES_AND_SCOPE.md`
  - Hard scope, non-negotiables, and completion criteria.
- `implementation-tasks/02_PHASED_EXECUTION_PLAN.md`
  - End-to-end implementation phases with explicit tasks.
- `implementation-tasks/03_COMPONENT_TASK_BREAKDOWN.md`
  - Detailed engineering tasks per system component.
- `implementation-tasks/04_OPERATION_IMPLEMENTATION_PLAYBOOK.md`
  - Exact per-operation implementation workflow template.
- `implementation-tasks/05_OPERATION_CHECKLIST_ALL_221.md`
  - Master checklist of all 221 Hetzner operations.
- `implementation-tasks/06_TEST_MATRIX_AND_ACCEPTANCE.md`
  - Full test strategy and acceptance gates.
- `implementation-tasks/07_COMMIT_PLAN_GRANULAR.md`
  - Small-commit execution sequence.
- `implementation-tasks/08_RISKS_EDGE_CASES_AND_MITIGATIONS.md`
  - Risk register and mitigation tasks.
- `implementation-tasks/09_README_DESIGN_SPEC.md`
  - README structure/design requirements in Aceternity style.

## How to execute this folder

1. Complete files in numeric order.
2. For each task item, create a small local commit.
3. Do not mark operation-level items complete unless tests for that item pass.
4. Do not ship until all acceptance gates in `06_TEST_MATRIX_AND_ACCEPTANCE.md` are green.
5. Do not claim "complete" unless all 221 operation checklist entries are implemented and validated.

## Status legend

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked

## Program-level objective

Deliver a production-grade MCP server named `hetzner-mcp` that exposes all Cloud + Storage operations from official Hetzner OpenAPI specs as robust, agent-friendly tools.
