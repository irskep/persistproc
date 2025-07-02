# Configuring Agents

AI agents connect to `persistproc` via its MCP (Multi-Agent Control Plane) endpoint. This guide covers how to configure them.

## The MCP Endpoint

The `persistproc` server exposes all of its process management tools via a single MCP endpoint. The URL for this endpoint is determined by the host and port the server is running on.

*   **Default URL**: `http://127.0.0.1:8947/mcp/`

If you start the server with custom arguments like `persistproc --serve --host 0.0.0.0 --port 9000`, the endpoint would be `http://0.0.0.0:9000/mcp/`.

## Connecting an Agent

To connect an AI agent, you must add the `persistproc` server's URL to your agent's MCP configuration.

### Cursor / VS Code

For editors like Cursor or VS Code with an MCP extension, this is done in your `settings.json` file.

1.  Open your `settings.json` file.
2.  Add the following JSON block, which tells the agent that a server named "persistproc" is available at the specified URL.

```json
{
  "mcp.servers": {
    "persistproc": {
      "url": "http://127.0.0.1:8947/mcp/"
    }
  }
}
```
3. Restart your editor to ensure the new settings are applied.

### Other MCP-Compatible Clients

Other clients that support the Model Context Protocol should have a similar mechanism for registering external tool servers. Refer to your specific tool's documentation for instructions on how to add an MCP server. You will always use the same `persistproc` MCP endpoint URL. 