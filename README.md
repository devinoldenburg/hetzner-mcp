<div align="center">

# Hetzner MCP

**Model Context Protocol server for full Hetzner Cloud + Storage API automation**

Expose all official Hetzner operations as MCP tools so AI agents can manage servers, networking, load balancers, firewalls, volumes, DNS zones, and storage boxes from one server.

[![PyPI](https://img.shields.io/pypi/v/hetzner-mcp.svg)](https://pypi.org/project/hetzner-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/hetzner-mcp.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compliant-1f6feb)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

</div>

---

## Install

```bash
pipx install hetzner-mcp
hetzner-mcp install
```

Then set your token and restart your MCP client:

```bash
export HETZNER_TOKEN="your_token_here"
```

Or configure it once via CLI (persisted local config):

```bash
hetzner-mcp auth set --token "your_token_here"
```

## What It Does

`hetzner-mcp` loads official OpenAPI specs from Hetzner and exposes operations as MCP tools.

- Full Cloud API coverage: `https://api.hetzner.cloud/v1`
- Full Storage API coverage: `https://api.hetzner.com/v1`
- Dynamic tool generation from operation IDs
- Helper tools for discovery, search, and operation schema inspection
- Action polling helper for async action workflows

### Core helper tools

| Tool | What it does |
|------|--------------|
| `list_api_operations` | List all operations with filters (domain/tag/method/query) |
| `search_api_operations` | Search operations by keyword |
| `get_api_operation_details` | Inspect full operation details and input schema |
| `list_api_categories` | List all API categories/tags with docs descriptions |
| `get_api_category_details` | Explain one category in depth with all endpoints inside |
| `list_api_projects` | Show configured project profiles and active credential context |
| `set_active_api_project` | Switch active project profile for agent execution context |
| `wait_for_action` | Poll cloud/storage actions until completion |

All API operations are also exposed directly as tools using the official operation ID names (for example `create_server`, `get_action`, `create_storage_box`).

For agent-friendly documentation, every endpoint and category also has dedicated guide tools:

- Endpoint guide tool pattern: `guide_<operation_id>`
  - Example: `guide_create_server`
- Category guide tool pattern: `category_guide_<api_domain>_<category_slug>`
  - Example: `category_guide_cloud_servers`

These guide tools include docs text from the OpenAPI documentation, explicit purpose, parameter explanations, and example tool arguments.

### Docs-first execution lock (required)

This server enforces a docs-first workflow for endpoint execution:

1. Call `guide_<operation_id>` first for the endpoint you want to execute.
2. Then call the endpoint tool itself (for example `create_server`).

If you skip step 1, execution is rejected with a `docs_required` error.

Unlocking is based on **context freshness** (interaction distance in the current session),
not wall-clock time:

- Docs must be read before execution.
- Recently executed endpoints remain trusted while context is still fresh.
- After enough unrelated tool interactions (context drift), docs must be read again.

## Full Coverage

Current generated operation coverage:

- Total operations: **221**
- Cloud operations: **189**
- Storage operations: **32**

You can verify this locally:

```bash
python scripts/verify_operation_coverage.py
```

## Example Prompts

```text
"List all Hetzner operations related to firewalls"
"Create a CX22 server in fsn1-dc14 with my SSH key"
"Attach volume 12345 to server 67890"
"Create a load balancer and add target server 1001"
"Enable rescue mode on server 123 and wait for action completion"
"Create a storage box and reset its password"
"Show operation details for update_storage_box_access_settings"
```

## Authentication

You can configure auth in two ways:

1) Environment variables (recommended for CI/ephemeral environments)
2) Local CLI config file (recommended for local workstation use)

Environment variables (highest precedence):

- `HETZNER_TOKEN` for both Cloud and Storage APIs
- `HETZNER_CLOUD_TOKEN` to override cloud auth token
- `HETZNER_STORAGE_TOKEN` to override storage auth token
- `HETZNER_PROJECT` to choose one configured local project profile for this session

Base URL safety:

- Default API targets are locked to the official Hetzner HTTPS endpoints.
- `HETZNER_CLOUD_BASE_URL` and `HETZNER_STORAGE_BASE_URL` are validated before any token is attached.
- Custom base URLs are blocked by default to prevent credential exfiltration to non-Hetzner hosts.
- For controlled test environments only, opt in explicitly with `HETZNER_ALLOW_CUSTOM_BASE_URLS=true`.

Local CLI config examples:

```bash
# set default token
hetzner-mcp auth set --token "your_token_here"

# auth set auto-probes what the provided key can do
# (cloud/storage + read/write capability hints)

# set per-domain overrides
hetzner-mcp auth set --cloud-token "cloud_token" --storage-token "storage_token"

# inspect effective token sources (env/file/unset)
hetzner-mcp auth show

# open full local config in your editor
hetzner-mcp config edit
```

Multi-project profile examples:

```bash
# create per-environment profiles
hetzner-mcp project add prod --description "Production Hetzner" --token "prod_token" --activate
hetzner-mcp project add staging --description "Staging Hetzner" --token "staging_token"

# project add also auto-detects capability hints for entered keys

# see which profile is active and what each one is for
hetzner-mcp project list

# switch active profile
hetzner-mcp project use staging
```

Capability probing notes:

- `auth set` and `project add` automatically probe entered keys and print capability hints.
- Report format includes per-domain read/write level plus probe status codes (for example `cloud:read+write`, `storage:no-access`).
- Detection uses safe representative `GET`/`POST` checks and is best-effort guidance, not a formal permission matrix.

Config file location:

- `~/.config/hetzner-mcp/config.json` (macOS/Linux)
- `%APPDATA%\\hetzner-mcp\\config.json` (Windows)
- Override path with `HETZNER_MCP_CONFIG_PATH`

Optional runtime controls:

- `HETZNER_CLOUD_BASE_URL`
- `HETZNER_STORAGE_BASE_URL`
- `HETZNER_TIMEOUT_SECONDS`
- `HETZNER_MAX_RETRIES`
- `HETZNER_BACKOFF_BASE_SECONDS`

## Supported MCP Clients

Auto-configuration is included for:

| Client | Auto-config |
|--------|-------------|
| Claude Desktop | Yes |
| Claude Code | Yes |
| Cursor | Yes |
| Cline | Yes |
| Windsurf | Yes |
| OpenCode | Yes |

Run:

```bash
hetzner-mcp install
```

OpenCode integration note:

- This installer writes OpenCode MCP config to the global OpenCode config file (`opencode.jsonc`) under the `mcp` key.
- Legacy `~/.opencode/mcp.json` is not used.

## Manual Configuration

```json
{
  "mcpServers": {
    "hetzner-mcp": {
      "command": "hetzner-mcp-server",
      "args": []
    }
  }
}
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `hetzner-mcp status` | Show effective runtime config + registry + client status |
| `hetzner-mcp doctor [--json]` | Print detailed diagnostics |
| `hetzner-mcp server run [--refresh-specs]` | Run stdio MCP server |
| `hetzner-mcp update` | Refresh specs and re-apply client integration |
| `hetzner-mcp client install` | Configure supported MCP clients |
| `hetzner-mcp client status` | Show client config installation state |
| `hetzner-mcp client repair` | Re-apply configuration entries |
| `hetzner-mcp client uninstall` | Remove MCP config entries |
| `hetzner-mcp auth set ...` | Configure API keys directly from CLI and auto-detect key capabilities |
| `hetzner-mcp auth show` | Show token status and source |
| `hetzner-mcp auth clear [--all]` | Clear stored token entries |
| `hetzner-mcp project add/list/show/use/remove` | Manage multiple project credential profiles (with capability probing on add) |
| `hetzner-mcp config show` | Show stored + effective config |
| `hetzner-mcp config get/set/unset <key>` | Read/write persisted config keys |
| `hetzner-mcp config edit` | Edit persisted config file in `$EDITOR` |

Legacy aliases still work: `install`, `repair`, `uninstall`, `diagnose`.

## Development

```bash
git clone https://github.com/devinoldenburg/hetzner-mcp.git
cd hetzner-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Validate quality
ruff check .
mypy src
pytest

# Refresh specs and inspect counts
python scripts/sync_specs.py
python scripts/verify_operation_coverage.py
```

## Security Notes

- Never commit API tokens.
- Tokens can be read from environment variables or persisted local config, but outbound API targets are validated before Authorization headers are sent.
- Official Hetzner HTTPS base URLs are enforced by default; custom base URLs require explicit opt-in with `HETZNER_ALLOW_CUSTOM_BASE_URLS=true`.
- Dynamic endpoint calls now validate path, query, and JSON body inputs against the loaded OpenAPI schema before making HTTP requests.
- MCP tool responses redact common secret fields such as `token`, `password`, `secret`, and `authorization` to avoid leaking credentials into transcripts.
- `set_active_api_project` now switches the active project for the current MCP session by default; use `persist=true` only when you intentionally want to update local config.
- Server logs are routed to stderr to keep stdio JSON-RPC clean.
- Network retries are limited and capped.

## Troubleshooting

**`ModuleNotFoundError: hetzner_mcp` in local scripts**

- Install editable package: `pip install -e .`

**No operations listed in MCP client**

- Run `hetzner-mcp status`
- Verify config file includes `hetzner-mcp`
- Restart the client process after installation

**Auth failures (`401 unauthorized`)**

- Ensure `HETZNER_TOKEN` or domain-specific token is exported in the client runtime environment

**Rate limiting (`429`)**

- The client retries transient failures automatically; reduce request burst and retry later

## License

MIT
