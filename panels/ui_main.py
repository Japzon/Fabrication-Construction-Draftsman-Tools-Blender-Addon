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
from .ui_ai_factory import LSD_PT_Generate
from .ui_parts import LSD_PT_Mechanical_Presets
from .ui_materials import LSD_PT_Materials_And_Textures
from .ui_lighting import LSD_PT_Lighting_And_Atmosphere
from . import ui_electronics
from .ui_electronics import LSD_PT_Electronic_Presets
from .ui_dimensions import LSD_PT_Dimensions_And_Precision_Transforms
from .ui_parametric import LSD_PT_Procedural_Toolkit
from .ui_architectural import LSD_PT_Architectural_Presets
from .ui_vehicle import LSD_PT_Vehicle_Presets
from .ui_physics import LSD_PT_Physics
from .ui_transmission import LSD_PT_Transmission
from .ui_kinematics import LSD_PT_Kinematics_Setup
from .ui_assets import LSD_PT_Asset_Library_System
from .ui_export import LSD_PT_Import_Export_System
from .ui_preferences import LSD_PT_Preferences
from .ui_camera import LSD_PT_Camera_Cinematography

class LSD_PT_FabricationConstructionDraftsmanTools(bpy.types.Panel):
    """
    The Master Panel that acts as a container for all other panels.
    It dynamically draws the sub-panels in the order defined by the user.
    """
    bl_label = "Layouts & Systems Draftsman Toolkit"
    bl_idname = "VIEW3D_PT_lsd_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Layouts & Systems Toolkit'
    bl_order = 0
    
    def draw(self, context):
        # Define the mapping of panels to their order properties
        panel_map = [
            (LSD_PT_Generate, "lsd_order_ai_factory"),
            (LSD_PT_Mechanical_Presets, "lsd_order_parts"),
            (LSD_PT_Architectural_Presets, "lsd_order_architectural"),
            (LSD_PT_Vehicle_Presets, "lsd_order_vehicle"),
            (LSD_PT_Electronic_Presets, "lsd_order_electronics"),
            (LSD_PT_Procedural_Toolkit, "lsd_order_procedural"),
            (LSD_PT_Dimensions_And_Precision_Transforms, "lsd_order_dimensions"),
            (LSD_PT_Materials_And_Textures, "lsd_order_materials"),
            (LSD_PT_Lighting_And_Atmosphere, "lsd_order_lighting"),
            (LSD_PT_Kinematics_Setup, "lsd_order_kinematics"),
            (LSD_PT_Camera_Cinematography, "lsd_order_camera"),
            (LSD_PT_Physics, "lsd_order_physics"),
            (LSD_PT_Transmission, "lsd_order_transmission"),
            (LSD_PT_Asset_Library_System, "lsd_order_assets"),
            (LSD_PT_Import_Export_System, "lsd_order_export"),
            (LSD_PT_Preferences, "lsd_order_preferences"),
        ]

        # Sort panels based on user-defined order
        panels_with_order = []
        for i, (panel_cls, prop_name) in enumerate(panel_map):
            user_order = getattr(context.scene, prop_name, i)
            panels_with_order.append((user_order, i, panel_cls))
        
        panels_with_order.sort(key=lambda x: (x[0], x[1]))
        
        # Draw each panel
        for _, _, panel_cls in panels_with_order:
            if hasattr(panel_cls, 'poll') and not panel_cls.poll(context):
                continue
            try:
                panel_cls.draw(self.layout, context)
            except Exception as e:
                import traceback
                err_box = self.layout.box()
                err_box.label(text=f"Panel error: {type(e).__name__}", icon='ERROR')
                print(f"[LSD Addon] Panel draw error in {panel_cls.__name__}: {e}")
                traceback.print_exc()

# ------------------------------------------------------------------------


def register():
    for cls in [LSD_PT_FabricationConstructionDraftsmanTools]:
        if hasattr(cls, 'bl_rna'):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass

def unregister():
    for cls in reversed([LSD_PT_FabricationConstructionDraftsmanTools]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

