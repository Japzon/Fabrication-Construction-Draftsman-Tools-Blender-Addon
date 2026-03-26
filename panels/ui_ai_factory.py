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

class URDF_PT_Generate:
    """
    Drawing helper for the 'Generate' panel. This is the central hub for
    spawning components using both AI-driven prompts and procedural templates.
    """
    bl_label = "Generate"
    bl_idname = "VIEW3D_PT_urdf_ai_factory"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return getattr(context.scene, "urdf_panel_enabled_ai_factory", True)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Generate Robot panel.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Generate", 
            "urdf_show_panel_ai_factory", 
            "urdf_panel_enabled_ai_factory"
        )
        
        if not is_expanded:
            return


        if is_expanded:
            # --- Global Scale Control ---
            cage_box = box.box()
            cage_box.label(text="Global Scale Constraint (Size Cage)", icon='SHADING_BBOX')
            cage_box.prop(scene, "urdf_use_generation_cage", text="Enable Size Cage")
            row = cage_box.row()
            row.enabled = scene.urdf_use_generation_cage
            row.prop(scene, "urdf_generation_cage_size", text="Max Dimension (L)")
            
            ai_props = scene.urdf_ai_props
            
            # --- Procedural Templates Section ---
            tmpl_box = box.box()
            tmpl_box.label(text="Structural / Mechanical Templates", icon='FILE_NEW')
            row = tmpl_box.row()
            row.prop(ai_props, "robot_template", text="Template")
            row.operator("urdf.generate_preset", text="Spawn Template", icon='IMPORT')
            
            box.separator()

            # --- AI Generation Hub ---
            api_box = box.box()
            api_box.label(text="AI Generator Configuration", icon='NODE_COMPOSITING')
            
            api_box.prop(ai_props, "ai_source", text="API Source")
            
            if ai_props.ai_source == 'API':
                api_box.prop(ai_props, "api_key", password=True)
            
            # --- Prompt Input ---
            prompt_box = box.box()
            prompt_box.label(text="AI Generation Prompt", icon='TEXT')
            prompt_box.prop(ai_props, "api_prompt", text="")
            
            # --- Execution ---
            box.separator()
            row = box.row()
            row.scale_y = 1.5
            row.operator("urdf.execute_ai_prompt", text="Generate via AI", icon='PLAY')


# ------------------------------------------------------------------------
#   PANEL: MECHANICAL PARTS GENERATOR
#   Order: 2
#   Description: Parametric generation of gears, chains, fasteners, etc.
# ------------------------------------------------------------------------

def register():
    pass

def unregister():
    pass

