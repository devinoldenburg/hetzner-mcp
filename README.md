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

Set one of the following:

- `HETZNER_TOKEN` for both Cloud and Storage APIs
- `HETZNER_CLOUD_TOKEN` to override cloud auth token
- `HETZNER_STORAGE_TOKEN` to override storage auth token

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
| `hetzner-mcp install` | Configure supported MCP clients |
| `hetzner-mcp status` | Show config + registry status |
| `hetzner-mcp diagnose` | Print diagnostics (supports `--json`) |
| `hetzner-mcp repair` | Re-apply configuration entries |
| `hetzner-mcp uninstall` | Remove MCP config entries |
| `hetzner-mcp server` | Run stdio MCP server |

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
- Tokens are read from environment variables.
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
