# QGIS MCP HTTP Plugin

## Install in QGIS

For local testing, copy this folder into your active QGIS profile plugins directory:

```bash
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/qgis_mcp_http
```

Restart QGIS, then enable **QGIS MCP HTTP** in **Plugins > Manage and Install Plugins**.

## Start the MCP Endpoint

Open **Plugins > QGIS MCP HTTP > QGIS MCP HTTP**, choose a port, and click **Start Server**.

The default endpoint is:

```text
http://127.0.0.1:9876/mcp
```

The server binds to `127.0.0.1` only.

## Codex Setup

```bash
codex mcp add qgis-http --url http://127.0.0.1:9876/mcp
```

Restart Codex after adding the server.

## Claude Desktop Setup

Claude Desktop currently works best with a small local proxy/wrapper for localhost Streamable HTTP MCP servers. A Fusion-style Claude Desktop Extension can point to:

```text
http://127.0.0.1:9876/mcp
```

## Exposed Tools

The plugin exposes the same tool surface as the original QGIS MCP command handlers:

- `ping`
- `get_qgis_info`
- `load_project`
- `create_new_project`
- `get_project_info`
- `add_vector_layer`
- `add_raster_layer`
- `get_layers`
- `remove_layer`
- `zoom_to_layer`
- `get_layer_features`
- `execute_processing`
- `save_project`
- `render_map`
