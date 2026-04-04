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

class LSD_PT_Generate:
    """
    Drawing helper for the 'Generate' panel. This is the central hub for
    spawning components using both AI-driven prompts and procedural templates.
    """
    bl_label = "Generate"
    bl_idname = "VIEW3D_PT_lsd_ai_factory"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return getattr(context.scene, "lsd_panel_enabled_ai_factory", True)

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
            "lsd_show_panel_ai_factory", 
            "lsd_panel_enabled_ai_factory"
        )
        
        if is_expanded:
            ai_props = scene.lsd_pg_ai_props
            
            # --- AI Configuration ---
            box.label(text="AI Configuration", icon='NODE_COMPOSITING')
            box.prop(ai_props, "ai_source", text="Source")
            
            if ai_props.ai_source == 'API':
                box.prop(ai_props, "api_key")
            
            # --- Prompt ---
            box.separator()
            box.label(text="Plain English Instruction", icon='TEXT')
            box.prop(ai_props, "api_prompt", text="")
            
            # --- Execution ---
            box.separator()
            row = box.row()
            row.scale_y = 1.6
            row.operator("lsd.execute_ai_prompt", text="Start Generating", icon='PLAY')


# ------------------------------------------------------------------------
#   PANEL: MECHANICAL PARTS GENERATOR
#   Order: 2
#   Description: Parametric generation of gears, chains, fasteners, etc.
# ------------------------------------------------------------------------

def register():
    pass

def unregister():
    pass

