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
from qgis.PyQt.QtGui import QIcon, QColor, QFont
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
                "zoom_to_extent": self.zoom_to_extent,
                "get_layer_features": self.get_layer_features,
                "get_layer_fields": self.get_layer_fields,
                "get_layer_statistics": self.get_layer_statistics,
                "set_layer_visibility": self.set_layer_visibility,
                "set_layer_opacity": self.set_layer_opacity,
                "rename_layer": self.rename_layer,
                "style_layer": self.style_layer,
                "set_graduated_renderer": self.set_graduated_renderer,
                "select_features_by_expression": self.select_features_by_expression,
                "edit_attribute": self.edit_attribute,
                "run_expression": self.run_expression,
                "execute_processing": self.execute_processing,
                "set_project_crs": self.set_project_crs,
                "list_layouts": self.list_layouts,
                "create_layout": self.create_layout,
                "add_layout_map": self.add_layout_map,
                "add_layout_label": self.add_layout_label,
                "add_layout_legend": self.add_layout_legend,
                "add_layout_picture": self.add_layout_picture,
                "add_layout_scale_bar": self.add_layout_scale_bar,
                "configure_atlas": self.configure_atlas,
                "get_atlas_info": self.get_atlas_info,
                "export_atlas": self.export_atlas,
                "export_layout": self.export_layout,
                "remove_layout": self.remove_layout,
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

    def _get_layer(self, layer_id):
        """Return a project layer or raise a helpful error."""
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            raise Exception(f"Layer not found: {layer_id}")
        return layer

    def _get_vector_layer(self, layer_id):
        """Return a vector layer or raise a helpful error."""
        layer = self._get_layer(layer_id)
        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Layer is not a vector layer: {layer_id}")
        return layer

    def _refresh_layer(self, layer):
        """Refresh a layer and the map canvas after visual changes."""
        try:
            layer.triggerRepaint()
        except Exception as e:
            QgsMessageLog.logMessage(f"Layer repaint failed: {str(e)}", "QGIS MCP", Qgis.Warning)

        if self.iface:
            self.iface.mapCanvas().refresh()

    def _parse_color(self, color, fallback="#3388ff"):
        """Parse a CSS-style color string into QColor."""
        qcolor = QColor(color or fallback)
        if not qcolor.isValid():
            raise Exception(f"Invalid color: {color}")
        return qcolor

    def _field_index(self, layer, field_name):
        index = layer.fields().indexFromName(field_name)
        if index < 0:
            raise Exception(f"Field not found: {field_name}")
        return index

    def _layout_by_name(self, name):
        manager = QgsProject.instance().layoutManager()
        layout = manager.layoutByName(name)
        if not layout:
            raise Exception(f"Layout not found: {name}")
        return layout

    def _layout_item_by_id(self, layout, item_id, expected_type=None):
        for item in layout.items():
            if hasattr(item, "id") and item.id() == item_id:
                if expected_type and not isinstance(item, expected_type):
                    raise Exception(f"Layout item is not a {expected_type.__name__}: {item_id}")
                return item
        raise Exception(f"Layout item not found: {item_id}")

    def _first_layout_map(self, layout):
        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                return item
        raise Exception(f"No map item found in layout: {layout.name()}")

    def _set_layout_item_id(self, item, item_id):
        if item_id and hasattr(item, "setId"):
            item.setId(item_id)
        return item.id() if hasattr(item, "id") else item_id

    def _layout_export_code(self, result):
        if isinstance(result, tuple):
            return result[0]
        return result

    def _layout_export_error(self, result):
        if isinstance(result, tuple) and len(result) > 1:
            return result[1]
        return ""
    
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

    def set_layer_visibility(self, layer_id, visible, **kwargs):
        """Set whether a layer is visible in the layer tree."""
        layer = self._get_layer(layer_id)
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        if not node:
            raise Exception(f"Layer tree node not found: {layer_id}")

        node.setItemVisibilityChecked(bool(visible))
        if self.iface:
            self.iface.mapCanvas().refresh()

        return {
            "layer_id": layer_id,
            "name": layer.name(),
            "visible": node.isVisible()
        }

    def set_layer_opacity(self, layer_id, opacity, **kwargs):
        """Set layer opacity between 0 and 1."""
        layer = self._get_layer(layer_id)
        opacity = float(opacity)
        if opacity < 0 or opacity > 1:
            raise Exception("Opacity must be between 0 and 1")

        if hasattr(layer, "setOpacity"):
            layer.setOpacity(opacity)
        elif layer.renderer() and hasattr(layer.renderer(), "setOpacity"):
            layer.renderer().setOpacity(opacity)
        else:
            raise Exception(f"Layer does not support opacity changes: {layer_id}")

        self._refresh_layer(layer)
        return {"layer_id": layer_id, "name": layer.name(), "opacity": opacity}

    def rename_layer(self, layer_id, name, **kwargs):
        """Rename a layer in the current project."""
        layer = self._get_layer(layer_id)
        old_name = layer.name()
        layer.setName(name)
        return {"layer_id": layer_id, "old_name": old_name, "name": layer.name()}
    
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

    def zoom_to_extent(self, xmin, ymin, xmax, ymax, crs=None, **kwargs):
        """Zoom the map canvas to an explicit extent."""
        rect = QgsRectangle(float(xmin), float(ymin), float(xmax), float(ymax))
        if crs:
            source_crs = QgsCoordinateReferenceSystem(crs)
            dest_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            if source_crs.isValid() and dest_crs.isValid() and source_crs != dest_crs:
                transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
                rect = transform.transformBoundingBox(rect)

        self.iface.mapCanvas().setExtent(rect)
        self.iface.mapCanvas().refresh()
        return {
            "extent": {
                "xmin": rect.xMinimum(),
                "ymin": rect.yMinimum(),
                "xmax": rect.xMaximum(),
                "ymax": rect.yMaximum()
            },
            "crs": self.iface.mapCanvas().mapSettings().destinationCrs().authid()
        }
    
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

    def get_layer_fields(self, layer_id, **kwargs):
        """Get vector layer field definitions."""
        layer = self._get_vector_layer(layer_id)
        fields = []
        for field in layer.fields():
            fields.append({
                "name": field.name(),
                "type": field.typeName(),
                "length": field.length(),
                "precision": field.precision(),
                "comment": field.comment()
            })

        return {"layer_id": layer_id, "fields": fields}

    def get_layer_statistics(self, layer_id, field_name, **kwargs):
        """Get summary statistics for a numeric vector field."""
        layer = self._get_vector_layer(layer_id)
        self._field_index(layer, field_name)

        values = []
        for feature in layer.getFeatures():
            value = feature.attribute(field_name)
            if value is not None:
                try:
                    values.append(float(value))
                except (TypeError, ValueError):
                    pass

        if not values:
            return {
                "layer_id": layer_id,
                "field_name": field_name,
                "count": 0,
                "message": "No numeric values found"
            }

        values.sort()
        count = len(values)
        total = sum(values)
        mean = total / count
        median = values[count // 2] if count % 2 else (values[count // 2 - 1] + values[count // 2]) / 2

        return {
            "layer_id": layer_id,
            "field_name": field_name,
            "count": count,
            "min": values[0],
            "max": values[-1],
            "sum": total,
            "mean": mean,
            "median": median
        }

    def select_features_by_expression(self, layer_id, expression, mode="replace", **kwargs):
        """Select vector features using a QGIS expression."""
        layer = self._get_vector_layer(layer_id)
        behavior_map = {
            "replace": QgsVectorLayer.SetSelection,
            "add": QgsVectorLayer.AddToSelection,
            "remove": QgsVectorLayer.RemoveFromSelection,
            "intersect": QgsVectorLayer.IntersectSelection,
        }
        behavior = behavior_map.get(mode)
        if behavior is None:
            raise Exception("Selection mode must be one of: replace, add, remove, intersect")

        layer.selectByExpression(expression, behavior)
        selected_ids = layer.selectedFeatureIds()

        return {
            "layer_id": layer_id,
            "selected_count": len(selected_ids),
            "selected_feature_ids": selected_ids[:1000],
            "truncated": len(selected_ids) > 1000
        }

    def edit_attribute(self, layer_id, feature_id, field_name, value, commit=True, **kwargs):
        """Edit a single feature attribute."""
        layer = self._get_vector_layer(layer_id)
        field_index = self._field_index(layer, field_name)
        feature_id = int(feature_id)
        was_editing = layer.isEditable()

        if not was_editing and not layer.startEditing():
            raise Exception(f"Could not start editing layer: {layer.name()}")

        if not layer.changeAttributeValue(feature_id, field_index, value):
            if not was_editing:
                layer.rollBack()
            raise Exception(f"Failed to update feature {feature_id} field {field_name}")

        committed = False
        if commit and not was_editing:
            if not layer.commitChanges():
                errors = layer.commitErrors()
                layer.rollBack()
                raise Exception(f"Failed to commit changes: {errors}")
            committed = True

        self._refresh_layer(layer)
        return {
            "layer_id": layer_id,
            "feature_id": feature_id,
            "field_name": field_name,
            "value": value,
            "committed": committed,
            "editing": layer.isEditable()
        }

    def run_expression(self, expression, layer_id=None, feature_id=None, **kwargs):
        """Evaluate a QGIS expression in project, layer, or feature context."""
        qgs_expression = QgsExpression(expression)
        if qgs_expression.hasParserError():
            raise Exception(qgs_expression.parserErrorString())

        context = QgsExpressionContext()
        scopes = [
            QgsExpressionContextUtils.globalScope(),
            QgsExpressionContextUtils.projectScope(QgsProject.instance())
        ]
        layer = None

        if layer_id:
            layer = self._get_vector_layer(layer_id)
            scopes.append(QgsExpressionContextUtils.layerScope(layer))

        context.appendScopes(scopes)

        if layer and feature_id is not None:
            request = QgsFeatureRequest(int(feature_id))
            feature = next(layer.getFeatures(request), None)
            if not feature:
                raise Exception(f"Feature not found: {feature_id}")
            context.setFeature(feature)
            context.setFields(layer.fields())

        value = qgs_expression.evaluate(context)
        if qgs_expression.hasEvalError():
            raise Exception(qgs_expression.evalErrorString())

        return {
            "expression": expression,
            "value": value,
            "value_type": type(value).__name__
        }

    def style_layer(self, layer_id, color="#3388ff", outline_color=None, opacity=1.0, line_width=0.5, marker_size=2.0, **kwargs):
        """Apply a simple single-symbol style to a vector layer or opacity to a raster layer."""
        layer = self._get_layer(layer_id)
        opacity = float(opacity)
        if opacity < 0 or opacity > 1:
            raise Exception("Opacity must be between 0 and 1")

        if layer.type() == QgsMapLayer.RasterLayer:
            return self.set_layer_opacity(layer_id, opacity)

        if layer.type() != QgsMapLayer.VectorLayer:
            raise Exception(f"Unsupported layer type for styling: {layer_id}")

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        if not symbol:
            raise Exception(f"Could not create a default symbol for layer: {layer_id}")

        symbol.setColor(self._parse_color(color))
        symbol.setOpacity(opacity)

        if hasattr(symbol, "setSize"):
            symbol.setSize(float(marker_size))
        if hasattr(symbol, "setWidth"):
            symbol.setWidth(float(line_width))

        for symbol_layer in symbol.symbolLayers():
            if outline_color and hasattr(symbol_layer, "setStrokeColor"):
                symbol_layer.setStrokeColor(self._parse_color(outline_color))
            if hasattr(symbol_layer, "setStrokeWidth"):
                symbol_layer.setStrokeWidth(float(line_width))

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        self._refresh_layer(layer)

        return {
            "layer_id": layer_id,
            "name": layer.name(),
            "renderer": "single_symbol",
            "color": color,
            "outline_color": outline_color,
            "opacity": opacity
        }

    def set_graduated_renderer(self, layer_id, field_name, classes=5, mode="quantile", color_ramp="Spectral", opacity=1.0, **kwargs):
        """Apply a graduated renderer to a vector layer."""
        layer = self._get_vector_layer(layer_id)
        self._field_index(layer, field_name)

        mode_map = {
            "equal_interval": QgsGraduatedSymbolRenderer.EqualInterval,
            "quantile": QgsGraduatedSymbolRenderer.Quantile,
            "natural_breaks": QgsGraduatedSymbolRenderer.Jenks,
            "jenks": QgsGraduatedSymbolRenderer.Jenks,
            "pretty": QgsGraduatedSymbolRenderer.Pretty,
            "stddev": QgsGraduatedSymbolRenderer.StdDev,
        }
        mode_enum = mode_map.get(mode)
        if mode_enum is None:
            raise Exception("Mode must be one of: equal_interval, quantile, natural_breaks, jenks, pretty, stddev")

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        if not symbol:
            raise Exception(f"Could not create a default symbol for layer: {layer_id}")
        symbol.setOpacity(float(opacity))

        ramp = QgsStyle.defaultStyle().colorRamp(color_ramp)
        if not ramp:
            ramp_names = QgsStyle.defaultStyle().colorRampNames()
            raise Exception(f"Color ramp not found: {color_ramp}. Available examples: {ramp_names[:20]}")

        renderer = QgsGraduatedSymbolRenderer()
        renderer.setClassAttribute(field_name)
        renderer.setSourceSymbol(symbol)
        renderer.setSourceColorRamp(ramp)
        renderer.updateClasses(layer, mode_enum, int(classes))
        layer.setRenderer(renderer)
        self._refresh_layer(layer)

        ranges = []
        for renderer_range in renderer.ranges():
            ranges.append({
                "lower": renderer_range.lowerValue(),
                "upper": renderer_range.upperValue(),
                "label": renderer_range.label()
            })

        return {
            "layer_id": layer_id,
            "field_name": field_name,
            "classes": int(classes),
            "mode": mode,
            "color_ramp": color_ramp,
            "ranges": ranges
        }
    
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

    def set_project_crs(self, crs, **kwargs):
        """Set the current project's coordinate reference system."""
        qgs_crs = QgsCoordinateReferenceSystem(crs)
        if not qgs_crs.isValid():
            raise Exception(f"Invalid CRS: {crs}")

        project = QgsProject.instance()
        project.setCrs(qgs_crs)
        if self.iface:
            self.iface.mapCanvas().setDestinationCrs(qgs_crs)
            self.iface.mapCanvas().refresh()

        return {"crs": project.crs().authid(), "description": project.crs().description()}

    def create_layout(self, name, page_size="A4", orientation="landscape", add_map=True, overwrite=False, **kwargs):
        """Create a QGIS print layout with an optional map item."""
        project = QgsProject.instance()
        manager = project.layoutManager()
        existing = manager.layoutByName(name)
        if existing:
            if not overwrite:
                raise Exception(f"Layout already exists: {name}")
            manager.removeLayout(existing)

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(name)

        page = layout.pageCollection().page(0)
        if page:
            size = QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters)
            if page_size.upper() == "A4" and orientation == "portrait":
                size = QgsLayoutSize(210, 297, QgsUnitTypes.LayoutMillimeters)
            page.attemptResize(size)

        if add_map:
            map_item = QgsLayoutItemMap(layout)
            map_item.setRect(20, 20, 250, 160)
            if self.iface:
                map_item.setExtent(self.iface.mapCanvas().extent())
            layout.addLayoutItem(map_item)
            map_item.attemptMove(QgsLayoutPoint(15, 20, QgsUnitTypes.LayoutMillimeters))
            map_item.attemptResize(QgsLayoutSize(267, 170, QgsUnitTypes.LayoutMillimeters))

        manager.addLayout(layout)
        return {
            "name": name,
            "layout_count": len(manager.layouts()),
            "add_map": bool(add_map)
        }

    def list_layouts(self, **kwargs):
        """List print layouts in the current project."""
        layouts = []
        for layout in QgsProject.instance().layoutManager().layouts():
            layout_type = type(layout).__name__
            if not hasattr(layout, "items"):
                layouts.append({
                    "name": layout.name(),
                    "type": layout_type,
                    "item_count": 0,
                    "atlas_enabled": False,
                    "items": [],
                    "items_truncated": False
                })
                continue

            atlas = layout.atlas() if hasattr(layout, "atlas") else None
            items = []
            for item in layout.items():
                item_type = type(item).__name__
                item_id = item.id() if hasattr(item, "id") else ""
                items.append({"type": item_type, "id": item_id})

            layouts.append({
                "name": layout.name(),
                "type": layout_type,
                "item_count": len(layout.items()),
                "atlas_enabled": bool(atlas and atlas.enabled()),
                "items": items[:50],
                "items_truncated": len(items) > 50
            })

        return {"layouts": layouts, "layout_count": len(layouts)}

    def add_layout_map(self, layout_name, item_id=None, x=10, y=10, width=180, height=160, layer_ids=None, extent=None, crs=None, atlas_driven=False, atlas_margin=0.10, **kwargs):
        """Add a map item to a print layout."""
        layout = self._layout_by_name(layout_name)
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, float(width), float(height))

        if layer_ids:
            layers = [self._get_layer(layer_id) for layer_id in layer_ids]
            map_item.setLayers(layers)

        if extent:
            rect = QgsRectangle(float(extent["xmin"]), float(extent["ymin"]), float(extent["xmax"]), float(extent["ymax"]))
            if crs:
                source_crs = QgsCoordinateReferenceSystem(crs)
                dest_crs = QgsProject.instance().crs()
                if source_crs.isValid() and dest_crs.isValid() and source_crs != dest_crs:
                    transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
                    rect = transform.transformBoundingBox(rect)
            map_item.setExtent(rect)
        elif self.iface:
            map_item.setExtent(self.iface.mapCanvas().extent())

        if atlas_driven:
            map_item.setAtlasDriven(True)
            if hasattr(map_item, "setAtlasScalingMode"):
                map_item.setAtlasScalingMode(QgsLayoutItemMap.Auto)
            if hasattr(map_item, "setAtlasMargin"):
                map_item.setAtlasMargin(float(atlas_margin))

        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(float(width), float(height), QgsUnitTypes.LayoutMillimeters))
        final_id = self._set_layout_item_id(map_item, item_id or "main_map")

        return {
            "layout": layout_name,
            "item_id": final_id,
            "atlas_driven": bool(atlas_driven),
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height)
        }

    def add_layout_label(self, layout_name, text, x=10, y=10, width=100, height=20, font_size=12, **kwargs):
        """Add a text label item to a print layout."""
        layout = self._layout_by_name(layout_name)
        label = QgsLayoutItemLabel(layout)
        label.setText(text)
        label.setFont(QFont("Arial", int(font_size)))
        label.adjustSizeToText()
        layout.addLayoutItem(label)
        label.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        label.attemptResize(QgsLayoutSize(float(width), float(height), QgsUnitTypes.LayoutMillimeters))

        return {
            "layout": layout_name,
            "text": text,
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height),
            "font_size": int(font_size)
        }

    def add_layout_legend(self, layout_name, title="Legend", x=10, y=40, width=60, height=80, **kwargs):
        """Add a legend item to a print layout."""
        layout = self._layout_by_name(layout_name)
        legend = QgsLayoutItemLegend(layout)
        legend.setTitle(title)
        legend.setLinkedMap(None)
        legend.model().setRootGroup(QgsProject.instance().layerTreeRoot())
        layout.addLayoutItem(legend)
        legend.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        legend.attemptResize(QgsLayoutSize(float(width), float(height), QgsUnitTypes.LayoutMillimeters))

        return {
            "layout": layout_name,
            "title": title,
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height)
        }

    def add_layout_picture(self, layout_name, path, item_id=None, x=10, y=10, width=30, height=30, **kwargs):
        """Add a picture/logo/SVG item to a print layout."""
        if not os.path.exists(path):
            raise Exception(f"Picture path does not exist: {path}")

        layout = self._layout_by_name(layout_name)
        picture = QgsLayoutItemPicture(layout)
        picture.setPicturePath(path)
        layout.addLayoutItem(picture)
        picture.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        picture.attemptResize(QgsLayoutSize(float(width), float(height), QgsUnitTypes.LayoutMillimeters))
        final_id = self._set_layout_item_id(picture, item_id)

        return {
            "layout": layout_name,
            "item_id": final_id,
            "path": path,
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height)
        }

    def add_layout_scale_bar(self, layout_name, map_item_id=None, style="Single Box", units="meters", x=10, y=180, width=60, height=15, units_per_segment=100, segments=2, left_segments=0, **kwargs):
        """Add a scale bar linked to a layout map item."""
        layout = self._layout_by_name(layout_name)
        map_item = self._layout_item_by_id(layout, map_item_id, QgsLayoutItemMap) if map_item_id else self._first_layout_map(layout)

        scale_bar = QgsLayoutItemScaleBar(layout)
        scale_bar.setStyle(style)
        scale_bar.setLinkedMap(map_item)
        scale_bar.setUnits(QgsUnitTypes.DistanceKilometers if units == "kilometers" else QgsUnitTypes.DistanceMeters)
        scale_bar.setUnitsPerSegment(float(units_per_segment))
        scale_bar.setNumberOfSegments(int(segments))
        scale_bar.setNumberOfSegmentsLeft(int(left_segments))
        layout.addLayoutItem(scale_bar)
        scale_bar.attemptMove(QgsLayoutPoint(float(x), float(y), QgsUnitTypes.LayoutMillimeters))
        scale_bar.attemptResize(QgsLayoutSize(float(width), float(height), QgsUnitTypes.LayoutMillimeters))
        scale_bar.update()

        return {
            "layout": layout_name,
            "map_item_id": map_item.id() if hasattr(map_item, "id") else map_item_id,
            "style": style,
            "units": units,
            "units_per_segment": float(units_per_segment),
            "segments": int(segments)
        }

    def configure_atlas(self, layout_name, coverage_layer_id, enabled=True, hide_coverage=True, page_name_expression=None, filter_expression=None, sort_expression=None, sort_ascending=True, filename_expression=None, map_item_id=None, **kwargs):
        """Configure atlas generation for a print layout."""
        layout = self._layout_by_name(layout_name)
        coverage_layer = self._get_vector_layer(coverage_layer_id)
        atlas = layout.atlas()

        atlas.setEnabled(bool(enabled))
        atlas.setCoverageLayer(coverage_layer)
        atlas.setHideCoverage(bool(hide_coverage))

        if page_name_expression is not None:
            atlas.setPageNameExpression(page_name_expression)
        if filename_expression is not None:
            atlas.setFilenameExpression(filename_expression)
        if filter_expression:
            atlas.setFilterFeatures(True)
            atlas.setFilterExpression(filter_expression)
        else:
            atlas.setFilterFeatures(False)
        if sort_expression:
            atlas.setSortFeatures(True)
            atlas.setSortExpression(sort_expression)
            atlas.setSortAscending(bool(sort_ascending))
        else:
            atlas.setSortFeatures(False)

        if map_item_id:
            map_item = self._layout_item_by_id(layout, map_item_id, QgsLayoutItemMap)
        else:
            map_item = None
            try:
                map_item = self._first_layout_map(layout)
            except Exception:
                map_item = None

        if map_item:
            map_item.setAtlasDriven(True)
            if hasattr(map_item, "setAtlasScalingMode"):
                map_item.setAtlasScalingMode(QgsLayoutItemMap.Auto)

        return {
            "layout": layout_name,
            "enabled": atlas.enabled(),
            "coverage_layer_id": coverage_layer_id,
            "coverage_layer_name": coverage_layer.name(),
            "hide_coverage": bool(hide_coverage),
            "page_name_expression": page_name_expression,
            "filter_expression": filter_expression,
            "sort_expression": sort_expression,
            "filename_expression": filename_expression,
            "map_item_id": map_item.id() if map_item and hasattr(map_item, "id") else None
        }

    def get_atlas_info(self, layout_name, **kwargs):
        """Get atlas configuration information for a layout."""
        layout = self._layout_by_name(layout_name)
        atlas = layout.atlas()
        coverage_layer = atlas.coverageLayer()

        return {
            "layout": layout_name,
            "enabled": atlas.enabled(),
            "coverage_layer_id": coverage_layer.id() if coverage_layer else None,
            "coverage_layer_name": coverage_layer.name() if coverage_layer else None,
            "hide_coverage": atlas.hideCoverage(),
            "page_name_expression": atlas.pageNameExpression(),
            "filter_features": atlas.filterFeatures(),
            "filter_expression": atlas.filterExpression(),
            "sort_features": atlas.sortFeatures(),
            "sort_expression": atlas.sortExpression(),
            "sort_ascending": atlas.sortAscending(),
            "filename_expression": atlas.filenameExpression()
        }

    def export_layout(self, name, path, format=None, dpi=300, **kwargs):
        """Export a QGIS print layout to PDF, image, or SVG."""
        layout = self._layout_by_name(name)
        exporter = QgsLayoutExporter(layout)
        export_format = (format or os.path.splitext(path)[1].lstrip(".") or "pdf").lower()

        if export_format == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            result = exporter.exportToPdf(path, settings)
        elif export_format in {"png", "jpg", "jpeg", "tif", "tiff"}:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = int(dpi)
            result = exporter.exportToImage(path, settings)
        elif export_format == "svg":
            settings = QgsLayoutExporter.SvgExportSettings()
            result = exporter.exportToSvg(path, settings)
        else:
            raise Exception("Format must be one of: pdf, png, jpg, jpeg, tif, tiff, svg")

        result_code = self._layout_export_code(result)
        if result_code != QgsLayoutExporter.Success:
            error = self._layout_export_error(result)
            detail = f": {error}" if error else ""
            raise Exception(f"Layout export failed with code: {result_code}{detail}")

        return {"layout": name, "path": path, "format": export_format, "dpi": int(dpi)}

    def export_atlas(self, layout_name, path, format=None, dpi=300, **kwargs):
        """Export all pages from a configured layout atlas."""
        layout = self._layout_by_name(layout_name)
        atlas = layout.atlas()
        if not atlas.enabled():
            raise Exception(f"Atlas is not enabled for layout: {layout_name}")
        if not atlas.coverageLayer():
            raise Exception(f"Atlas coverage layer is not configured for layout: {layout_name}")

        exporter = QgsLayoutExporter(layout)
        export_format = (format or os.path.splitext(path)[1].lstrip(".") or "pdf").lower()

        if export_format == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            result = exporter.exportToPdf(atlas, path, settings)
        elif export_format in {"png", "jpg", "jpeg", "tif", "tiff"}:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = int(dpi)
            base_path, extension = os.path.splitext(path)
            extension = extension.lstrip(".") or export_format
            result = exporter.exportToImage(atlas, base_path, extension, settings)
        else:
            raise Exception("Atlas format must be one of: pdf, png, jpg, jpeg, tif, tiff")

        result_code = self._layout_export_code(result)
        if result_code != QgsLayoutExporter.Success:
            error = self._layout_export_error(result)
            detail = f": {error}" if error else ""
            raise Exception(f"Atlas export failed with code: {result_code}{detail}")

        return {
            "layout": layout_name,
            "path": path,
            "format": export_format,
            "dpi": int(dpi),
            "coverage_layer": atlas.coverageLayer().name()
        }

    def remove_layout(self, name, **kwargs):
        """Remove a print layout from the current project."""
        manager = QgsProject.instance().layoutManager()
        layout = manager.layoutByName(name)
        if not layout:
            raise Exception(f"Layout not found: {name}")

        manager.removeLayout(layout)
        return {"removed": name, "layout_count": len(manager.layouts())}
    
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
MCP_SERVER_VERSION = "0.3.2"
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
        "name": "zoom_to_extent",
        "description": "Zoom the map canvas to an explicit extent, optionally transforming from a source CRS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "xmin": {"type": "number"},
                "ymin": {"type": "number"},
                "xmax": {"type": "number"},
                "ymax": {"type": "number"},
                "crs": {"type": "string"},
            },
            "required": ["xmin", "ymin", "xmax", "ymax"],
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
        "name": "get_layer_fields",
        "description": "Retrieve field definitions for a vector layer.",
        "inputSchema": {
            "type": "object",
            "properties": {"layer_id": {"type": "string"}},
            "required": ["layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_layer_statistics",
        "description": "Calculate summary statistics for a numeric vector layer field.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "field_name": {"type": "string"},
            },
            "required": ["layer_id", "field_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_layer_visibility",
        "description": "Set whether a layer is visible in the layer tree.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "visible": {"type": "boolean"},
            },
            "required": ["layer_id", "visible"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_layer_opacity",
        "description": "Set layer opacity between 0 and 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "opacity": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["layer_id", "opacity"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rename_layer",
        "description": "Rename a layer in the current project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["layer_id", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "style_layer",
        "description": "Apply a simple single-symbol style to a vector layer, or opacity to a raster layer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "color": {"type": "string", "default": "#3388ff"},
                "outline_color": {"type": "string"},
                "opacity": {"type": "number", "default": 1, "minimum": 0, "maximum": 1},
                "line_width": {"type": "number", "default": 0.5, "minimum": 0},
                "marker_size": {"type": "number", "default": 2, "minimum": 0},
            },
            "required": ["layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_graduated_renderer",
        "description": "Apply a graduated renderer to a vector layer field.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "field_name": {"type": "string"},
                "classes": {"type": "integer", "default": 5, "minimum": 2, "maximum": 20},
                "mode": {
                    "type": "string",
                    "default": "quantile",
                    "enum": ["equal_interval", "quantile", "natural_breaks", "jenks", "pretty", "stddev"]
                },
                "color_ramp": {"type": "string", "default": "Spectral"},
                "opacity": {"type": "number", "default": 1, "minimum": 0, "maximum": 1},
            },
            "required": ["layer_id", "field_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "select_features_by_expression",
        "description": "Select vector features using a QGIS expression.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "expression": {"type": "string"},
                "mode": {
                    "type": "string",
                    "default": "replace",
                    "enum": ["replace", "add", "remove", "intersect"]
                },
            },
            "required": ["layer_id", "expression"],
            "additionalProperties": False,
        },
    },
    {
        "name": "edit_attribute",
        "description": "Edit a single feature attribute on a vector layer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layer_id": {"type": "string"},
                "feature_id": {"type": "integer"},
                "field_name": {"type": "string"},
                "value": {},
                "commit": {"type": "boolean", "default": True},
            },
            "required": ["layer_id", "feature_id", "field_name", "value"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_expression",
        "description": "Evaluate a QGIS expression in project, layer, or feature context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "layer_id": {"type": "string"},
                "feature_id": {"type": "integer"},
            },
            "required": ["expression"],
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
        "name": "set_project_crs",
        "description": "Set the current project's coordinate reference system.",
        "inputSchema": {
            "type": "object",
            "properties": {"crs": {"type": "string"}},
            "required": ["crs"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_layout",
        "description": "Create a QGIS print layout with an optional map item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "page_size": {"type": "string", "default": "A4"},
                "orientation": {"type": "string", "default": "landscape", "enum": ["landscape", "portrait"]},
                "add_map": {"type": "boolean", "default": True},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_layout_map",
        "description": "Add a map item to a print layout, optionally atlas-driven.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "item_id": {"type": "string"},
                "x": {"type": "number", "default": 10},
                "y": {"type": "number", "default": 10},
                "width": {"type": "number", "default": 180, "minimum": 1},
                "height": {"type": "number", "default": 160, "minimum": 1},
                "layer_ids": {"type": "array", "items": {"type": "string"}},
                "extent": {
                    "type": "object",
                    "properties": {
                        "xmin": {"type": "number"},
                        "ymin": {"type": "number"},
                        "xmax": {"type": "number"},
                        "ymax": {"type": "number"},
                    },
                    "required": ["xmin", "ymin", "xmax", "ymax"],
                    "additionalProperties": False,
                },
                "crs": {"type": "string"},
                "atlas_driven": {"type": "boolean", "default": False},
                "atlas_margin": {"type": "number", "default": 0.10, "minimum": 0},
            },
            "required": ["layout_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_layouts",
        "description": "List print layouts in the current project.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "add_layout_label",
        "description": "Add a text label item to a print layout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "text": {"type": "string"},
                "x": {"type": "number", "default": 10},
                "y": {"type": "number", "default": 10},
                "width": {"type": "number", "default": 100, "minimum": 1},
                "height": {"type": "number", "default": 20, "minimum": 1},
                "font_size": {"type": "integer", "default": 12, "minimum": 1},
            },
            "required": ["layout_name", "text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_layout_legend",
        "description": "Add a legend item to a print layout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "title": {"type": "string", "default": "Legend"},
                "x": {"type": "number", "default": 10},
                "y": {"type": "number", "default": 40},
                "width": {"type": "number", "default": 60, "minimum": 1},
                "height": {"type": "number", "default": 80, "minimum": 1},
            },
            "required": ["layout_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_layout_picture",
        "description": "Add a picture, logo, or SVG item to a print layout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "path": {"type": "string"},
                "item_id": {"type": "string"},
                "x": {"type": "number", "default": 10},
                "y": {"type": "number", "default": 10},
                "width": {"type": "number", "default": 30, "minimum": 1},
                "height": {"type": "number", "default": 30, "minimum": 1},
            },
            "required": ["layout_name", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_layout_scale_bar",
        "description": "Add a scale bar linked to a layout map item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "map_item_id": {"type": "string"},
                "style": {"type": "string", "default": "Single Box"},
                "units": {"type": "string", "default": "meters", "enum": ["meters", "kilometers"]},
                "x": {"type": "number", "default": 10},
                "y": {"type": "number", "default": 180},
                "width": {"type": "number", "default": 60, "minimum": 1},
                "height": {"type": "number", "default": 15, "minimum": 1},
                "units_per_segment": {"type": "number", "default": 100, "minimum": 0},
                "segments": {"type": "integer", "default": 2, "minimum": 1},
                "left_segments": {"type": "integer", "default": 0, "minimum": 0},
            },
            "required": ["layout_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "configure_atlas",
        "description": "Configure atlas generation for a print layout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "coverage_layer_id": {"type": "string"},
                "enabled": {"type": "boolean", "default": True},
                "hide_coverage": {"type": "boolean", "default": True},
                "page_name_expression": {"type": "string"},
                "filter_expression": {"type": "string"},
                "sort_expression": {"type": "string"},
                "sort_ascending": {"type": "boolean", "default": True},
                "filename_expression": {"type": "string"},
                "map_item_id": {"type": "string"},
            },
            "required": ["layout_name", "coverage_layer_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_atlas_info",
        "description": "Get atlas configuration information for a layout.",
        "inputSchema": {
            "type": "object",
            "properties": {"layout_name": {"type": "string"}},
            "required": ["layout_name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "export_layout",
        "description": "Export a QGIS print layout to PDF, image, or SVG.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string"},
                "format": {"type": "string", "enum": ["pdf", "png", "jpg", "jpeg", "tif", "tiff", "svg"]},
                "dpi": {"type": "integer", "default": 300, "minimum": 1},
            },
            "required": ["name", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "export_atlas",
        "description": "Export all pages from a configured layout atlas to PDF or images.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "layout_name": {"type": "string"},
                "path": {"type": "string"},
                "format": {"type": "string", "enum": ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]},
                "dpi": {"type": "integer", "default": 300, "minimum": 1},
            },
            "required": ["layout_name", "path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remove_layout",
        "description": "Remove a print layout from the current project.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
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
