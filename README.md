# QGIS MCP HTTP

QGIS MCP HTTP exposes the active QGIS desktop session as a localhost-only Streamable HTTP Model Context Protocol (MCP) server.

The plugin is intended for MCP clients such as Codex, Claude Desktop wrappers, and other local automation tools that need to inspect and control QGIS through a standard MCP endpoint.

## Status And Attribution

This repository is prepared for QGIS plugin registry testing. The command handlers are copied from the existing [`jjsantos01/qgis_mcp`](https://github.com/jjsantos01/qgis_mcp) QGIS plugin implementation, with permission, so the known-working QGIS tool behavior is preserved while the transport changes from a separate socket/stdout bridge to direct Streamable HTTP.

This derivative is licensed under GPL-2.0.

## Install from ZIP

Create a plugin ZIP with the plugin folder at the top level:

```bash
zip -r qgis_mcp_http-0.3.1.zip qgis_mcp_http \
  -x '*/__pycache__/*' '*.pyc' '*.DS_Store' '*/.git/*'
```

In QGIS:

1. Open **Plugins > Manage and Install Plugins...**
2. Open **Install from ZIP**
3. Select the generated ZIP file
4. Enable **QGIS MCP HTTP**
5. Open **Plugins > QGIS MCP HTTP > QGIS MCP HTTP**
6. Click **Start Server**

The default endpoint is:

```text
http://127.0.0.1:9876/mcp
```

## Codex

```bash
codex mcp add qgis-http --url http://127.0.0.1:9876/mcp
```

Restart Codex after adding the server.

## Tools

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
- `zoom_to_extent`
- `get_layer_features`
- `get_layer_fields`
- `get_layer_statistics`
- `set_layer_visibility`
- `set_layer_opacity`
- `rename_layer`
- `style_layer`
- `set_graduated_renderer`
- `select_features_by_expression`
- `edit_attribute`
- `run_expression`
- `execute_processing`
- `set_project_crs`
- `create_layout`
- `add_layout_map`
- `list_layouts`
- `add_layout_label`
- `add_layout_legend`
- `add_layout_picture`
- `add_layout_scale_bar`
- `configure_atlas`
- `get_atlas_info`
- `export_layout`
- `export_atlas`
- `remove_layout`
- `save_project`
- `render_map`
