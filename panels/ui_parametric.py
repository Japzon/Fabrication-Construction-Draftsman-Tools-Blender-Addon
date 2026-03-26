import bpy
import bmesh
import math
import mathutils
import re
import os
import json
import xml.etree.ElementTree as ET
import gpu
from bpy.app.handlers import persistent
from operator import itemgetter
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from typing import List, Tuple, Optional, Set, Any, Dict
from .. import config
from ..config import *
from .. import core
from .. import properties
from .. import operators
from . import ui_common

class URDF_PT_ParametricToolkit:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Parametric Toolkit' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.urdf_panel_enabled_parametric

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        # AI Editor Note: The panel header now uses a dedicated operator to toggle
        # its expanded state. This prevents unintended expansions on hover,
        # ensuring the update logic (like auto-collapse) only runs on explicit clicks.
        # The `prop` is still used for the visual toggle icon.
        is_expanded = scene.urdf_show_panel_parametric
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Parametric Toolkit", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_parametric"
        row.prop(scene, "urdf_show_panel_parametric", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_parametric"


        if is_expanded:
            # --- Section: Parametric Anchors (Moved to Top) ---
            anchor_box = box.box()
            anchor_box.label(text="Parametric Anchors", icon='HOOK')
            if context.mode == 'EDIT_MESH':
                # AI Editor Note: Swapped icons and renamed marker operator per user request.
                anchor_box.operator("urdf.add_parametric_anchor", text="Attach Hook to Selected", icon='SPHERE')
                anchor_box.operator("urdf.add_marker", text="Attach Marker to Vertex", icon='EMPTY_AXIS')
            else:
                if context.active_object and context.active_object.type == 'EMPTY':
                    if context.scene.urdf_hook_placement_mode:
                        anchor_box.operator("urdf.toggle_hook_placement", text="Stop Hook Placement Mode", icon='CHECKMARK')
                    else:
                        anchor_box.operator("urdf.toggle_hook_placement", text="Start Hook Placement Mode", icon='TRANSFORM_ORIGINS')
                    
                    # AI Editor Note: Updated UI layout per user request.
                    anchor_box.operator("urdf.bake_anchor", text="Update Selected Objects with Hooks", icon='MODIFIER_ON')
                    anchor_box.operator("urdf.cleanup_anchor", text="Remove Selected Hook/Marker", icon='TRASH')
                elif context.active_object and context.active_object.type == 'MESH':
                     # AI Editor Note: Check for hooks to show update button
                     has_hooks = False
                     for mod in context.active_object.modifiers:
                         if mod.type == 'HOOK':
                             has_hooks = True
                             break
                     
                     if has_hooks:
                         anchor_box.operator("urdf.bake_anchor", text="Update Selected Objects with Hooks", icon='MODIFIER_ON')

                     anchor_box.label(text="Enter Edit Mode to add anchors", icon='INFO')
                else:
                    anchor_box.label(text="Enter Edit Mode to add anchors", icon='INFO')



            # --- Section: Hard Surface Modifiers ---
            # These operators add standard Blender modifiers for common modeling tasks.
            features_box = box.box()
            features_box.label(text="Hard Surface Modifiers", icon='MODIFIER')
            row = features_box.row(align=True)
            row.operator("urdf.add_parametric_mod", text="Fillet/Chamfer").type = 'BEVEL'
            row.operator("urdf.add_parametric_mod", text="Shell/Thicken").type = 'SOLIDIFY'
            row = features_box.row(align=True)
            row.operator("urdf.add_parametric_mod", text="Revolve").type = 'SCREW'
            row.operator("urdf.add_parametric_mod", text="Mirror").type = 'MIRROR'

            # --- Section: Boolean Operations ---
            bool_box = box.box()
            bool_box.label(text="Boolean Operations", icon='MOD_BOOLEAN')
            row = bool_box.row(align=True)
            row.operator("urdf.add_boolean", text="Cut").operation = 'DIFFERENCE'
            row.operator("urdf.add_boolean", text="Join").operation = 'UNION'
            row.operator("urdf.add_boolean", text="Intersect").operation = 'INTERSECT'

            # --- Section: Patterns ---
            pattern_box = box.box()
            pattern_box.label(text="Patterns", icon='MOD_ARRAY')
            row = pattern_box.row(align=True)
            row.operator("urdf.setup_linear_array", text="Linear Pattern")
            row.operator("urdf.setup_radial_array", text="Radial Pattern")

            # New row for curve-based patterns, providing a clear workflow.
            curve_row = pattern_box.row(align=True)
            
            # 1. A dropdown menu to create a new curve of a specific type.
            curve_row.operator_menu_enum("urdf.create_curve_for_path", "type", text="Create Curve", icon='CURVE_PATH')
            
            # 2. The 'Follow Curve' operator now assigns the selected object(s) to the active curve.
            # Its icon signifies assignment, and it's disabled if the selection is invalid.
            curve_row.operator_menu_enum("urdf.setup_curve_array", "mode", text="Follow Curve", icon='HOOK')

            # --- Section: Geometry Cleanup ---
            cleanup_box = box.box()
            cleanup_box.label(text="Geometry Cleanup", icon='BRUSH_DATA')
            row = cleanup_box.row(align=True)
            row.operator("urdf.add_simplify", text="Weld (Merge)").mode = 'WELD'
            row.operator("urdf.add_simplify", text="Decimate (Simplify)").mode = 'COLLAPSE'
            row.operator("urdf.add_simplify", text="Quad-ify").mode = 'QUADIFY'

            # --- Section: Shading ---
            shading_box = box.box()
            shading_box.label(text="Shading", icon='SHADING_RENDERED')
            shading_box.operator("urdf.smart_smooth", text="Smart Smooth (Auto Weighted)")

            # The modifier stack UI has been removed. Blender's native Properties Editor
            # provides a complete and stable interface for managing modifiers, making a
            # duplicate UI in this panel redundant and prone to errors.
            
            # --- AI Editor Note: Physics properties are not drawn in this panel ---
            # This panel is for general solid modeling tools that apply to any active object.
            # Physics properties are specific to kinematic links or generated parts and are
            # available in the 'Kinematics Setup' and 'Generate Mechanical Parts' panels respectively.


def register():
    for cls in [URDF_PT_ParametricToolkit]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_ParametricToolkit]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)
