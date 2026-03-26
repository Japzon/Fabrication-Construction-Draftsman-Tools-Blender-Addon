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

class URDF_PT_Generate:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Generate Robot' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """
    # AI Editor Note: Renamed panel to "Generate Robot" and updated order to be above Mechanical Parts.
    bl_label = "Generate"
    bl_idname = "VIEW3D_PT_urdf_ai_factory"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.urdf_panel_enabled_ai_factory

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        # AI Editor Note: The panel header now uses a dedicated operator to toggle
        # its expanded state. This prevents unintended expansions on hover,
        # ensuring the update logic (like auto-collapse) only runs on explicit clicks.
        # The `prop` is still used for the visual toggle icon.
        is_expanded = scene.urdf_show_panel_ai_factory
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Generate", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_ai_factory"
        row.prop(scene, "urdf_show_panel_ai_factory", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_ai_factory"


        if is_expanded:
            # AI Editor Note: Add the Generation Size Cage feature to this panel.
            cage_box = box.box()
            cage_box.label(text="Generation Size Constraint", icon='SHADING_BBOX')
            cage_box.prop(scene, "urdf_use_generation_cage")
            row = cage_box.row()
            row.enabled = scene.urdf_use_generation_cage
            row.prop(scene, "urdf_generation_cage_size")
            
            ai_props = scene.urdf_ai_props
            
            # --- Templates Section ---
            tmpl_box = box.box()
            tmpl_box.label(text="Quick Templates (No AI)", icon='FILE_NEW')
            row = tmpl_box.row()
            row.prop(ai_props, "robot_template", text="")
            row.operator("urdf.generate_preset", text="Load Template", icon='IMPORT')
            
            box.separator()

            # --- API Settings ---
            api_box = box.box()
            api_box.label(text="API Configuration", icon='KEYINGSET')
            
            # AI Editor Note: Added source selection dropdown.
            api_box.prop(ai_props, "ai_source", text="Source")
            
            # Only show API key field if API source is selected.
            if ai_props.ai_source == 'API':
                api_box.prop(ai_props, "api_key")
            
            # --- Prompt Input ---
            prompt_box = box.box()
            prompt_box.label(text="Prompt", icon='TEXT')
            
            # Use a larger text box for the prompt by setting `text=""`
            # and letting the property's name act as the label above.
            # This is a standard Blender UI trick for multi-line text input.
            prompt_box.prop(ai_props, "api_prompt", text="")
            
            # --- Execution Button ---
            box.separator()
            row = box.row()
            # Make the button larger for emphasis
            row.scale_y = 1.5
            row.operator("urdf.execute_ai_prompt", icon='PLAY')


# ------------------------------------------------------------------------
#   PANEL: MECHANICAL PARTS GENERATOR
#   Order: 2
#   Description: Parametric generation of gears, chains, fasteners, etc.
# ------------------------------------------------------------------------

def register():
    pass

def unregister():
    pass
