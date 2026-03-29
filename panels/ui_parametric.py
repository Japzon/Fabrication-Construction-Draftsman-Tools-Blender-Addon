# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# Licensed under the GNU General Public License (GPL).
# Original Architecture & Logic by Greenlex Systems Services Incorporated.
#
# No person or organization is authorized to misrepresent this work or claim 
# original authorship for themselves. Proper attribution is mandatory.
# --------------------------------------------------------------------------------




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

class FCD_PT_Procedural_Toolkit:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Procedural Toolkit' panel. It is not a
    registered bpy.types.Panel, but is called by the main FCD_PT_FabricationConstructionDraftsmanTools
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.fcd_panel_enabled_procedural

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        # --- Header ---
        box, is_expanded = ui_common.draw_panel_header(layout, context, "Procedural Toolkit", "fcd_show_panel_procedural", "fcd_panel_enabled_procedural")


        if is_expanded:



            # --- Section: Hard Surface Modifiers ---
            # These operators add standard Blender modifiers for common modeling tasks.
            features_box = box.box()
            features_box.label(text="Hard Surface Modifiers", icon='MODIFIER')
            row = features_box.row(align=True)
            row.operator("fcd.add_parametric_mod", text="Fillet/Chamfer").type = 'BEVEL'
            row.operator("fcd.add_parametric_mod", text="Shell/Thicken").type = 'SOLIDIFY'
            row = features_box.row(align=True)
            row.operator("fcd.add_parametric_mod", text="Revolve").type = 'SCREW'
            row.operator("fcd.add_parametric_mod", text="Mirror").type = 'MIRROR'

            # --- Section: Boolean Operations ---
            bool_box = box.box()
            bool_box.label(text="Boolean Operations", icon='MOD_BOOLEAN')
            row = bool_box.row(align=True)
            row.operator("fcd.add_boolean", text="Cut").operation = 'DIFFERENCE'
            row.operator("fcd.add_boolean", text="Join").operation = 'UNION'
            row.operator("fcd.add_boolean", text="Intersect").operation = 'INTERSECT'

            # --- Section: Patterns ---
            pattern_box = box.box()
            pattern_box.label(text="Patterns", icon='MOD_ARRAY')
            row = pattern_box.row(align=True)
            row.operator("fcd.setup_linear_array", text="Linear Pattern")
            row.operator("fcd.setup_radial_array", text="Radial Pattern")

            # New row for curve-based patterns, providing a clear workflow.
            curve_row = pattern_box.row(align=True)
            
            # 1. A dropdown menu to create a new curve of a specific type.
            curve_row.operator_menu_enum("fcd.create_curve_for_path", "type", text="Create Curve", icon='CURVE_PATH')
            
            # 2. The 'Follow Curve' operator now assigns the selected object(s) to the active curve.
            # Its icon signifies assignment, and it's disabled if the selection is invalid.
            curve_row.operator_menu_enum("fcd.setup_curve_array", "mode", text="Follow Curve", icon='HOOK')

            # --- Section: Geometry Cleanup ---
            cleanup_box = box.box()
            cleanup_box.label(text="Geometry Cleanup", icon='BRUSH_DATA')
            row = cleanup_box.row(align=True)
            row.operator("fcd.add_simplify", text="Weld (Merge)").mode = 'WELD'
            row.operator("fcd.add_simplify", text="Decimate (Simplify)").mode = 'COLLAPSE'
            row.operator("fcd.add_simplify", text="Quad-ify").mode = 'QUADIFY'

            # --- Section: Shading ---
            shading_box = box.box()
            shading_box.label(text="Shading", icon='SHADING_RENDERED')
            shading_box.operator("fcd.smart_smooth", text="Smart Smooth (Auto Weighted)")

            # The modifier stack UI has been removed. Blender's native Properties Editor
            # provides a complete and stable interface for managing modifiers, making a
            # duplicate UI in this panel redundant and prone to errors.
            
            # --- AI Editor Note: Physics properties are not drawn in this panel ---
            # This panel is for general solid modeling tools that apply to any active object.
            # Physics properties are specific to kinematic links or generated parts and are
            # available in the 'Kinematics Setup' and 'Generate Mechanical Parts' panels respectively.


def register():
    for cls in [FCD_PT_Procedural_Toolkit]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([FCD_PT_Procedural_Toolkit]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

