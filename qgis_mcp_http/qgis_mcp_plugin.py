# QGIS MCP HTTP
# Copyright (C) 2026 Aaron Mineen
# Derived with permission from jjsantos01/qgis_mcp.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import os
import json
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import QObject, pyqtSignal, QTimer, Qt, QSize
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QVBoxLayout, QLabel, QPushButton, QSpinBox, QWidget
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.utils import active_plugins

class QgisMCPServer(QObject):
    """Server class to handle socket connections and execute QGIS commands"""
    
    def __init__(self, host='localhost', port=9876, iface=None):
        super().__init__()
        self.host = host
        self.port = port
        self.iface = iface
        self.running = False
        self.socket = None
        self.client = None
        self.buffer = b''
        self.timer = None
    
    def start(self):
        """Start the server"""
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.socket.setblocking(False)
            
            # Create a timer to process server operations
            self.timer = QTimer()
            self.timer.timeout.connect(self.process_server)
            self.timer.start(100)  # 100ms interval
            
            QgsMessageLog.logMessage(f"QGIS MCP server started on {self.host}:{self.port}", "QGIS MCP")
            return True
        except Exception as e:
            QgsMessageLog.logMessage(f"Failed to start server: {str(e)}", "QGIS MCP", Qgis.Critical)
            self.stop()
            return False
            
    def stop(self):
        """Stop the server"""
        self.running = False
        
        if self.timer:
            self.timer.stop()
            self.timer = None
            
        if self.socket:
            self.socket.close()
        if self.client:
            self.client.close()
            
        self.socket = None
        self.client = None
        QgsMessageLog.logMessage("QGIS MCP server stopped", "QGIS MCP")
    
    def process_server(self):
        """Process server operations (called by timer)"""
        if not self.running:
            return
            
        try:
            # Accept new connections
            if not self.client and self.socket:
                try:
                    self.client, address = self.socket.accept()
                    self.client.setblocking(False)
                    QgsMessageLog.logMessage(f"Connected to client: {address}", "QGIS MCP")
                except BlockingIOError:
                    pass  # No connection waiting
                except Exception as e:
                    QgsMessageLog.logMessage(f"Error accepting connection: {str(e)}", "QGIS MCP", Qgis.Warning)
                
            # Process existing connection
            if self.client:
                try:
                    # Try to receive data
                    try:
                        data = self.client.recv(8192)
                        if data:
                            self.buffer += data
                            # Try to process complete messages
                            try:
                                # Attempt to parse the buffer as JSON
                                command = json.loads(self.buffer.decode('utf-8'))
                                # If successful, clear the buffer and process command
                                self.buffer = b''
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                self.client.sendall(response_json.encode('utf-8'))
                            except json.JSONDecodeError:
                                # Incomplete data, keep in buffer
                                pass
                        else:
                            # Connection closed by client
                            QgsMessageLog.logMessage("Client disconnected", "QGIS MCP")
                            self.client.close()
                            self.client = None
                            self.buffer = b''
                    except BlockingIOError:
                        pass  # No data available
                    except Exception as e:
                        QgsMessageLog.logMessage(f"Error receiving data: {str(e)}", "QGIS MCP", Qgis.Warning)
                        self.client.close()
                        self.client = None
                        self.buffer = b''
                        
                except Exception as e:
                    QgsMessageLog.logMessage(f"Error with client: {str(e)}", "QGIS MCP", Qgis.Warning)
                    if self.client:
                        self.client.close()
                        self.client = None
                    self.buffer = b''
                    
        except Exception as e:
            QgsMessageLog.logMessage(f"Server error: {str(e)}", "QGIS MCP", Qgis.Critical)

    def execute_command(self, command):
        """Execute a command"""
        try:
            cmd_type = command.get("type")
            params = command.get("params", {})
            
            handlers = {
                "ping": self.ping,
                "get_qgis_info": self.get_qgis_info,
                "load_project": self.load_project,
                "get_project_info": self.get_project_info,
                "add_vector_layer": self.add_vector_layer,
                "add_raster_layer": self.add_raster_layer,
                "get_layers": self.get_layers,
                "remove_layer": self.remove_layer,
                "zoom_to_layer": self.zoom_to_layer,
                "get_layer_features": self.get_layer_features,
                "execute_processing": self.execute_processing,
                "save_project": self.save_project,
                "render_map": self.render_map,
                "create_new_project": self.create_new_project,
            }
            
            handler = handlers.get(cmd_type)
            if handler:
                try:
                    QgsMessageLog.logMessage(f"Executing handler for {cmd_type}", "QGIS MCP")
                    result = handler(**params)
                    QgsMessageLog.logMessage(f"Handler execution complete", "QGIS MCP")
                    return {"status": "success", "result": result}
                except Exception as e:
                    QgsMessageLog.logMessage(f"Error in handler: {str(e)}", "QGIS MCP", Qgis.Critical)
                    traceback.print_exc()
                    return {"status": "error", "message": str(e)}
            else:
                return {"status": "error", "message": f"Unknown command type: {cmd_type}"}
                
        except Exception as e:
            QgsMessageLog.logMessage(f"Error executing command: {str(e)}", "QGIS MCP", Qgis.Critical)
            traceback.print_exc()
            return {"status": "error", "message": str(e)}
    
    # Command handlers
    def ping(self, **kwargs):
        """Simple ping command"""
        return {"pong": True}
    
    def get_qgis_info(self, **kwargs):
        """Get basic QGIS information"""
        return {
            "qgis_version": Qgis.version(),
            "profile_folder": QgsApplication.qgisSettingsDirPath(),
            "plugins_count": len(active_plugins)
        }
    
    def get_project_info(self, **kwargs):
        """Get information about the current QGIS project"""
        project = QgsProject.instance()
        
        # Get basic project information
        info = {
            "filename": project.fileName(),
            "title": project.title(),
            "layer_count": len(project.mapLayers()),
            "crs": project.crs().authid(),
            "layers": []
        }
        
        # Add basic layer information (limit to 10 layers for performance)
        layers = list(project.mapLayers().values())
        for i, layer in enumerate(layers):
            if i >= 10:  # Limit to 10 layers
                break
                
            layer_info = {
                "id": layer.id(),
                "name": layer.name(),
                "type": self._get_layer_type(layer),
                "visible": layer.isValid() and project.layerTreeRoot().findLayer(layer.id()).isVisible()
            }
            info["layers"].append(layer_info)
        
        return info
    
    def _get_layer_type(self, layer):
        """Helper to get layer type as string"""
        if layer.type() == QgsMapLayer.VectorLayer:
            return f"vector_{layer.geometryType()}"
        elif layer.type() == QgsMapLayer.RasterLayer:
            return "raster"
        else:
            return str(layer.type())
    
    def add_vector_layer(self, path, name=None, provider="ogr", **kwargs):
        """Add a vector layer to the project"""
        if not name:
            name = os.path.basename(path)
            
        # Create the layer
        layer = QgsVectorLayer(path, name, provider)
        
        if not layer.isValid():
            raise Exception(f"Layer is not valid: {path}")
        
        # Add to project
        QgsProject.instance().addMapLayer(layer)
        
        return {
            "id": layer.id(),
            "name": layer.name(),
            "type": self._get_layer_type(layer),
            "feature_count": layer.featureCount()
        }
    
    def add_raster_layer(self, path, name=None, provider="gdal", **kwargs):
        """Add a raster layer to the project"""
        if not name:
            name = os.path.basename(path)
            
        # Create the layer
        layer = QgsRasterLayer(path, name, provider)
        
        if not layer.isValid():
            raise Exception(f"Layer is not valid: {path}")
        
        # Add to project
        QgsProject.instance().addMapLayer(layer)
        
        return {
            "id": layer.id(),
            "name": layer.name(),
            "type": "raster",
            "width": layer.width(),
            "height": layer.height()
        }
    
    def get_layers(self, **kwargs):
        """Get all layers in the project"""
        project = QgsProject.instance()
        layers = []
        
        for layer_id, layer in project.mapLayers().items():
            layer_info = {
                "id": layer_id,
                "name": layer.name(),
                "type": self._get_layer_type(layer),
                "visible": project.layerTreeRoot().findLayer(layer_id).isVisible()
            }
            
            # Add type-specific information
            if layer.type() == QgsMapLayer.VectorLayer:
                layer_info.update({
                    "feature_count": layer.featureCount(),
                    "geometry_type": layer.geometryType()
                })
            elif layer.type() == QgsMapLayer.RasterLayer:
                layer_info.update({
                    "width": layer.width(),
                    "height": layer.height()
                })
                
            layers.append(layer_info)
        
        return layers
    
    def remove_layer(self, layer_id, **kwargs):
        """Remove a layer from the project"""
        project = QgsProject.instance()
        
        if layer_id in project.mapLayers():
            project.removeMapLayer(layer_id)
            return {"removed": layer_id}
        else:
            raise Exception(f"Layer not found: {layer_id}")
    
    def zoom_to_layer(self, layer_id, **kwargs):
        """Zoom to a layer's extent"""
        project = QgsProject.instance()
        
        if layer_id in project.mapLayers():
            layer = project.mapLayer(layer_id)
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()
            return {"zoomed_to": layer_id}
        else:
            raise Exception(f"Layer not found: {layer_id}")
    
    def get_layer_features(self, layer_id, limit=10, **kwargs):
        """Get features from a vector layer"""
        project = QgsProject.instance()
        
        if layer_id in project.mapLayers():
            layer = project.mapLayer(layer_id)
            
            if layer.type() != QgsMapLayer.VectorLayer:
                raise Exception(f"Layer is not a vector layer: {layer_id}")
            
            features = []
            for i, feature in enumerate(layer.getFeatures()):
                if i >= limit:
                    break
                    
                # Extract attributes
                attrs = {}
                for field in layer.fields():
                    attrs[field.name()] = feature.attribute(field.name())
                
                # Extract geometry if available
                geom = None
                if feature.hasGeometry():
                    geom = {
                        "type": feature.geometry().type(),
                        "wkt": feature.geometry().asWkt(precision=4)
                    }
                
                features.append({
                    "id": feature.id(),
                    "attributes": attrs,
                    "geometry": geom
                })
            
            return {
                "layer_id": layer_id,
                "feature_count": layer.featureCount(),
                "features": features,
                "fields": [field.name() for field in layer.fields()]
            }
        else:
            raise Exception(f"Layer not found: {layer_id}")
    
    def execute_processing(self, algorithm, parameters, **kwargs):
        """Execute a processing algorithm"""
        try:
            import processing
            result = processing.run(algorithm, parameters)
            return {
                "algorithm": algorithm,
                "result": {k: str(v) for k, v in result.items()}  # Convert values to strings for JSON
            }
        except Exception as e:
            raise Exception(f"Processing error: {str(e)}")
    
    def save_project(self, path=None, **kwargs):
        """Save the current project"""
        project = QgsProject.instance()
        
        if not path and not project.fileName():
            raise Exception("No project path specified and no current project path")
        
        save_path = path if path else project.fileName()
        if project.write(save_path):
            return {"saved": save_path}
        else:
            raise Exception(f"Failed to save project to {save_path}")
    
    def load_project(self, path, **kwargs):
        """Load a project"""
        project = QgsProject.instance()
        
        if project.read(path):
            self.iface.mapCanvas().refresh()
            return {
                "loaded": path,
                "layer_count": len(project.mapLayers())
            }
        else:
            raise Exception(f"Failed to load project from {path}")
    
    def create_new_project(self, path, **kwargs):
        """
        Creates a new QGIS project and saves it at the specified path.
        If a project is already loaded, it clears it before creating the new one.
        
        :param project_path: Full path where the project will be saved
                            (e.g., 'C:/path/to/project.qgz')
        """
        project = QgsProject.instance()
        
        if project.fileName():
            project.clear()
        
        project.setFileName(path)
        self.iface.mapCanvas().refresh()
        
        # Save the project
        if project.write():
            return {
                "created": f"Project created and saved successfully at: {path}",
                "layer_count": len(project.mapLayers())
            }
        else:
            raise Exception(f"Failed to save project to {path}")
    
    def render_map(self, path, width=800, height=600, **kwargs):
        """Render the current map view to an image"""
        try:
            # Create map settings
            ms = QgsMapSettings()
            
            # Set layers to render
            layers = list(QgsProject.instance().mapLayers().values())
            ms.setLayers(layers)
            
            # Set map canvas properties
            rect = self.iface.mapCanvas().extent()
            ms.setExtent(rect)
            ms.setOutputSize(QSize(width, height))
            ms.setBackgroundColor(QColor(255, 255, 255))
            ms.setOutputDpi(96)
            
            # Create the render
            render = QgsMapRendererParallelJob(ms)
            
            # Start rendering
            render.start()
            render.waitForFinished()
            
            # Get the image and save
            img = render.renderedImage()
            if img.save(path):
                return {
                    "rendered": True,
                    "path": path,
                    "width": width,
                    "height": height
                }
            else:
                raise Exception(f"Failed to save rendered image to {path}")
                
        except Exception as e:
            raise Exception(f"Render error: {str(e)}")


MCP_SERVER_NAME = "QGIS MCP HTTP"
MCP_SERVER_VERSION = "0.1.1"
SUPPORTED_MCP_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]

MCP_TOOLS = [
    {
        "name": "ping",
        "description": "Simple ping command to check server connectivity.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_qgis_info",
        "description": "Get QGIS information.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "load_project",
        "description": "Load a QGIS project from the specified path.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_new_project",
        "description": "Create a new project and save it.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_project_info",
        "description": "Get current project information.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "add_vector_layer",
        "description": "Add a vector layer to the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "provider": {"type": "string", "default": "ogr"},
                "name": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_raster_layer",
        "description": "Add a raster layer to the project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "provider": {"type": "string", "default": "gdal"},
                "name": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_layers",
        "description": "Retrieve all layers in the current project.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "remove_layer",
        "description": "Remove a layer from the project by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"layer_id": {"type": "string"}},
            "required": ["layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "zoom_to_layer",
        "description": "Zoom to the extent of a specified layer.",
        "inputSchema": {
            "type": "object",
            "properties": {"layer_id": {"type": "string"}},
            "required": ["layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_layer_features",
        "description": "Retrieve features from a vector layer with an optional limit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10, "minimum": 1},
            },
            "required": ["layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "execute_processing",
        "description": "Execute a processing algorithm with the given parameters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "algorithm": {"type": "string"},
                "parameters": {"type": "object"},
            },
            "required": ["algorithm", "parameters"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_project",
        "description": "Save the current project to the given path, or to the current project path if not specified.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "render_map",
        "description": "Render the current map view to an image file with the specified dimensions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "width": {"type": "integer", "default": 800, "minimum": 1},
                "height": {"type": "integer", "default": 600, "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]

MCP_TOOL_NAMES = {tool["name"] for tool in MCP_TOOLS}


class MCPCommandRequest:
    """Request envelope used to execute copied QGIS handlers on the Qt thread."""

    def __init__(self, command_type, params):
        self.command_type = command_type
        self.params = params or {}
        self.event = threading.Event()
        self.response = None


class QgisMCPRequestBridge(QObject):
    """Bridge HTTP worker threads to QGIS's main Qt thread."""

    command_requested = pyqtSignal(object)

    def __init__(self, iface):
        super().__init__()
        self.command_runner = QgisMCPServer(iface=iface)
        self.command_requested.connect(self._execute_request, Qt.QueuedConnection)

    def execute(self, command_type, params=None, timeout=120):
        request = MCPCommandRequest(command_type, params)
        self.command_requested.emit(request)

        if not request.event.wait(timeout):
            return {
                "status": "error",
                "message": f"Timed out executing QGIS command: {command_type}",
            }

        return request.response

    def _execute_request(self, request):
        try:
            request.response = self.command_runner.execute_command(
                {"type": request.command_type, "params": request.params}
            )
        except Exception as e:
            request.response = {"status": "error", "message": str(e)}
        finally:
            request.event.set()


class QgisMCPHttpServer:
    """Streamable HTTP MCP server exposed directly from the copied QGIS plugin."""

    def __init__(self, host="127.0.0.1", port=9876, iface=None):
        self.host = host
        self.port = port
        self.iface = iface
        self.running = False
        self.httpd = None
        self.thread = None
        self.bridge = QgisMCPRequestBridge(iface)

    @property
    def endpoint(self):
        return f"http://{self.host}:{self.port}/mcp"

    def start(self):
        if self.running:
            return True

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), QgisMCPHttpRequestHandler)
            self.httpd.qgis_mcp_server = self
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            QgsMessageLog.logMessage(f"QGIS MCP HTTP server started at {self.endpoint}", "QGIS MCP HTTP")
            return True
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Failed to start QGIS MCP HTTP server: {str(e)}",
                "QGIS MCP HTTP",
                Qgis.Critical,
            )
            self.stop()
            return False

    def stop(self):
        self.running = False

        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Error stopping QGIS MCP HTTP server: {str(e)}",
                    "QGIS MCP HTTP",
                    Qgis.Warning,
                )

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

        self.httpd = None
        self.thread = None
        QgsMessageLog.logMessage("QGIS MCP HTTP server stopped", "QGIS MCP HTTP")

    def handle_json_rpc(self, message):
        if isinstance(message, list):
            responses = [self.handle_json_rpc(item) for item in message]
            return [response for response in responses if response is not None]

        if not isinstance(message, dict):
            return self._json_rpc_error(None, -32600, "Invalid Request")

        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}

        if method == "initialize":
            return self._json_rpc_result(request_id, self._initialize_result(params))

        if method == "notifications/initialized":
            return None

        if method == "ping":
            return self._json_rpc_result(request_id, {})

        if method == "tools/list":
            return self._json_rpc_result(request_id, {"tools": MCP_TOOLS})

        if method == "tools/call":
            return self._handle_tool_call(request_id, params)

        return self._json_rpc_error(request_id, -32601, f"Method not found: {method}")

    def _initialize_result(self, params):
        requested_protocol = params.get("protocolVersion")
        protocol = requested_protocol if requested_protocol in SUPPORTED_MCP_PROTOCOLS else SUPPORTED_MCP_PROTOCOLS[0]

        return {
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
        }

    def _handle_tool_call(self, request_id, params):
        name = params.get("name")
        arguments = params.get("arguments") or {}

        if not name:
            return self._json_rpc_error(request_id, -32602, "Missing tool name")

        if name not in MCP_TOOL_NAMES:
            return self._json_rpc_error(request_id, -32602, f"Unknown tool: {name}")

        result = self.bridge.execute(name, arguments)
        is_error = result.get("status") == "error"

        return self._json_rpc_result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2, default=str),
                    }
                ],
                "isError": is_error,
            },
        )

    def _json_rpc_result(self, request_id, result):
        if request_id is None:
            return None

        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _json_rpc_error(self, request_id, code, message):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


class QgisMCPHttpRequestHandler(BaseHTTPRequestHandler):
    server_version = "QgisMCPHTTP/0.1"

    def do_OPTIONS(self):
        if self.path_is_mcp_endpoint():
            self.send_response(204)
            self.send_mcp_headers()
            self.end_headers()
        else:
            self.send_error(404)

    def do_HEAD(self):
        if self.path_is_mcp_endpoint():
            self.send_response(405)
            self.send_header("Allow", "POST, OPTIONS")
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.write_json({"status": "ok", "endpoint": self.mcp_server.endpoint})
            return

        if self.path_is_mcp_endpoint():
            self.send_response(405)
            self.send_header("Allow", "POST, OPTIONS")
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.path_is_mcp_endpoint():
            self.send_error(404)
            return

        if not self.origin_is_allowed():
            self.send_error(403, "Origin is not allowed")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            message = json.loads(body.decode("utf-8"))
        except Exception:
            self.write_json(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                status=400,
            )
            return

        response = self.mcp_server.handle_json_rpc(message)
        if response is None or response == []:
            self.send_response(202)
            self.send_mcp_headers()
            self.end_headers()
            return

        self.write_json(response)

    @property
    def mcp_server(self):
        return self.server.qgis_mcp_server

    def path_is_mcp_endpoint(self):
        return urlparse(self.path).path == "/mcp"

    def origin_is_allowed(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True

        parsed = urlparse(origin)
        return parsed.hostname in {"localhost", "127.0.0.1", "::1"}

    def send_mcp_headers(self):
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id")
        self.send_header("Cache-Control", "no-store")

    def write_json(self, payload, status=200):
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_mcp_headers()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        QgsMessageLog.logMessage(format % args, "QGIS MCP HTTP")


class QgisMCPDockWidget(QDockWidget):
    """Dock widget for the QGIS MCP plugin"""
    closed = pyqtSignal()
    
    def __init__(self, iface):
        super().__init__("QGIS MCP HTTP")
        self.iface = iface
        self.server = None
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the dock widget UI"""
        # Create widget and layout
        widget = QWidget()
        layout = QVBoxLayout()
        widget.setLayout(layout)
        
        # Add port selection
        layout.addWidget(QLabel("MCP HTTP Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setMinimum(1024)
        self.port_spin.setMaximum(65535)
        self.port_spin.setValue(9876)
        layout.addWidget(self.port_spin)
        
        # Add server control buttons
        self.start_button = QPushButton("Start Server")
        self.start_button.clicked.connect(self.start_server)
        layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Server")
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.setEnabled(False)
        layout.addWidget(self.stop_button)
        
        # Add status label
        self.status_label = QLabel("Server: Stopped")
        layout.addWidget(self.status_label)

        self.endpoint_label = QLabel("Endpoint: not running")
        self.endpoint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.endpoint_label.setWordWrap(True)
        layout.addWidget(self.endpoint_label)
        
        # Add to dock widget
        self.setWidget(widget)
    
    def start_server(self):
        """Start the server"""
        if not self.server:
            port = self.port_spin.value()
            self.server = QgisMCPHttpServer(port=port, iface=self.iface)
            
        if self.server.start():
            self.status_label.setText(f"Server: Running on port {self.server.port}")
            self.endpoint_label.setText(f"Endpoint: {self.server.endpoint}")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.port_spin.setEnabled(False)
    
    def stop_server(self):
        """Stop the server"""
        if self.server:
            self.server.stop()
            self.server = None
            
        self.status_label.setText("Server: Stopped")
        self.endpoint_label.setText("Endpoint: not running")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.port_spin.setEnabled(True)
        
    def closeEvent(self, event):
        """Stop server on dock close"""
        self.stop_server()
        self.closed.emit()
        super().closeEvent(event)


class QgisMCPPlugin:
    """Main plugin class for QGIS MCP HTTP"""
    
    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.action = None
    
    def initGui(self):
        """Initialize GUI"""
        # Create action
        self.action = QAction(
            "QGIS MCP HTTP",
            self.iface.mainWindow()
        )
        self.action.setCheckable(True)
        self.action.triggered.connect(self.toggle_dock)
        
        # Add to plugins menu and toolbar
        self.iface.addPluginToMenu("QGIS MCP HTTP", self.action)
        self.iface.addToolBarIcon(self.action)
    
    def toggle_dock(self, checked):
        """Toggle the dock widget"""
        if checked:
            # Create dock widget if it doesn't exist
            if not self.dock_widget:
                self.dock_widget = QgisMCPDockWidget(self.iface)
                self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
                # Connect close event
                self.dock_widget.closed.connect(self.dock_closed)
            else:
                # Show existing dock widget
                self.dock_widget.show()
        else:
            # Hide dock widget
            if self.dock_widget:
                self.dock_widget.hide()
    
    def dock_closed(self):
        """Handle dock widget closed"""
        self.action.setChecked(False)
    
    def unload(self):
        """Unload plugin"""
        # Stop server if running
        if self.dock_widget:
            self.dock_widget.stop_server()
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget = None
            
        # Remove plugin menu item and toolbar icon
        self.iface.removePluginMenu("QGIS MCP HTTP", self.action)
        self.iface.removeToolBarIcon(self.action)


# Plugin entry point
def classFactory(iface):
    return QgisMCPPlugin(iface)
