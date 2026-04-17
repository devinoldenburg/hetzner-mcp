# README Design Spec (Aceternity MCP Style)

This file defines the target README structure and content requirements.

## 1) Hero block requirements

- [ ] Centered title: `Hetzner MCP`.
- [ ] One-line value proposition.
- [ ] 2-3 sentence product pitch.
- [ ] Badge row (version, Python, MCP, license, tests).

## 2) Fast install section

- [ ] `pipx install hetzner-mcp`
- [ ] `hetzner-mcp install`
- [ ] short restart instruction for MCP clients.

## 3) What it does section

- [ ] Table describing key tools:
  - dynamic operation tools (221)
  - list/search/detail helper tools
  - optional action wait helper
- [ ] Mention full support for cloud + storage APIs.

## 4) Full coverage section

- [ ] Explicitly state `221 operations` total.
- [ ] Show breakdown:
  - cloud: 189
  - storage: 32
- [ ] Include per-tag summary table.

## 5) Example prompts section

- [ ] Add realistic prompts for:
  - servers lifecycle
  - firewall updates
  - load balancer operations
  - volume attach/resize
  - storage box snapshot/subaccount workflows

## 6) Supported clients section

- [ ] Table with auto-config support for:
  - Claude Desktop
  - Claude Code
  - Cursor
  - Cline
  - Windsurf
  - OpenCode
- [ ] Add manual configuration JSON example.

## 7) Authentication/config section

- [ ] Explain required env vars.
- [ ] Show examples for shell export.
- [ ] Include warning not to commit tokens.

## 8) CLI command section

- [ ] Document install/status/update/repair/diagnose/uninstall commands.
- [ ] Add examples for repair flags.

## 9) Development section

- [ ] Local setup instructions.
- [ ] Lint/type/test commands.
- [ ] How to sync specs and rebuild registry.

## 10) Security section

- [ ] Explain token handling and redaction.
- [ ] Explain API request safety defaults.

## 11) Troubleshooting section

- [ ] Common issues and fixes:
  - command not found
  - token missing/invalid
  - MCP server not showing in client
  - throttling/rate limit issues

## 12) Quality bar for README completion

- [ ] A new user can install and make first successful tool call using README alone.
- [ ] All command examples reflect real shipped command names.
- [ ] Coverage numbers match generated operation registry.
