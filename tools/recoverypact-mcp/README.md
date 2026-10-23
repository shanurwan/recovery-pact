# recoverypact-mcp

Read-only MCP server for post-incident review of RecoveryPact eval results inside Cursor.
Agreement is not permission: these tools never start a live incident, never call the
executor or a model provider, and never read `.env`.

## Cursor setup

This workspace already registers the server in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "recoverypact": {
      "command": "python",
      "args": ["tools/recoverypact-mcp/server.py"]
    }
  }
}
```

1. `pip install -r tools/recoverypact-mcp/requirements.txt`
2. Reload MCP servers in Cursor (Settings → MCP, or restart the agent).
3. Confirm the five tools appear under the `recoverypact` server.

Paths resolve from the repo root (parent of `tools/`), so the working directory does not matter.

## Tools

| Tool | Purpose |
|---|---|
| `list_runs` | Table of runs from `evals/results/<label>/summary.json` |
| `explain_run` | Decision story: evidence → negotiation → authority → verifier → audit |
| `compare_arms` | Pact vs `gated_single` vs `naive_single` for one scenario |
| `validate_results` | Independent validator (`VALID` / `INVALID` + first errors) |
| `verify_receipts` | Nightshift receipt join + signature summary |

## Example questions

1. *List the wrong runs in the ultra-benchmark.* → `list_runs(only_wrong=True)`
2. *Explain why the pact did not terminate in incident B of the ultra benchmark.* → `explain_run` on the pact B `run_id`
3. *Why do two guardians matter on protected settlement?* → `compare_arms("B")`
4. *Is the ultra-benchmark result set still valid?* → `validate_results("ultra-benchmark")`
5. *Did Nightshift sign the Nemotron calls for this label?* → `verify_receipts("ultra-benchmark")`

## Tests

```bash
pip install -r tools/recoverypact-mcp/requirements.txt
pytest tools/recoverypact-mcp -q
```
