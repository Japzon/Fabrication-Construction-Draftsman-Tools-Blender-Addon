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
from .ui_ai_factory import FCD_PT_Generate
from .ui_parts import FCD_PT_Mechanical_Presets
from .ui_materials import FCD_PT_Materials_And_Textures
from .ui_lighting import FCD_PT_Lighting_And_Atmosphere
from . import ui_electronics
from .ui_electronics import FCD_PT_Electronic_Presets
from .ui_dimensions import FCD_PT_Dimensions_And_Precision_Transforms
from .ui_parametric import FCD_PT_Procedural_Toolkit
from .ui_architectural import FCD_PT_Architectural_Presets
from .ui_vehicle import FCD_PT_Vehicle_Presets
from .ui_inertial import FCD_PT_Physics_Inertial
from .ui_collision import FCD_PT_Physics_Collision
from .ui_transmission import FCD_PT_Transmission
from .ui_kinematics import FCD_PT_Kinematics_Setup
from .ui_assets import FCD_PT_Asset_Library_System
from .ui_export import FCD_PT_Import_Export_System
from .ui_preferences import FCD_PT_Preferences
from .ui_camera import FCD_PT_Camera_Cinematography

class FCD_PT_FabricationConstructionDraftsmanTools(bpy.types.Panel):
    """
    The Master Panel that acts as a container for all other panels.
    It dynamically draws the sub-panels in the order defined by the user.
    """
    bl_label = "Fabrication & Construction Draftsman Tools"
    bl_idname = "VIEW3D_PT_fcd_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Draftsman Tools'
    bl_order = 0
    
    def draw(self, context):
        # Define the mapping of panels to their order properties
        panel_map = [
            (FCD_PT_Generate, "fcd_order_ai_factory"),
            (FCD_PT_Mechanical_Presets, "fcd_order_parts"),
            (FCD_PT_Architectural_Presets, "fcd_order_architectural"),
            (FCD_PT_Vehicle_Presets, "fcd_order_vehicle"),
            (FCD_PT_Electronic_Presets, "fcd_order_electronics"),
            (FCD_PT_Procedural_Toolkit, "fcd_order_procedural"),
            (FCD_PT_Dimensions_And_Precision_Transforms, "fcd_order_dimensions"),
            (FCD_PT_Materials_And_Textures, "fcd_order_materials"),
            (FCD_PT_Lighting_And_Atmosphere, "fcd_order_lighting"),
            (FCD_PT_Kinematics_Setup, "fcd_order_kinematics"),
            (FCD_PT_Camera_Cinematography, "fcd_order_camera"),
            (FCD_PT_Physics_Inertial, "fcd_order_inertial"),
            (FCD_PT_Physics_Collision, "fcd_order_collision"),
            (FCD_PT_Transmission, "fcd_order_transmission"),
            (FCD_PT_Asset_Library_System, "fcd_order_assets"),
            (FCD_PT_Import_Export_System, "fcd_order_export"),
            (FCD_PT_Preferences, "fcd_order_preferences"),
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
                print(f"[FCD Addon] Panel draw error in {panel_cls.__name__}: {e}")
                traceback.print_exc()

# ------------------------------------------------------------------------


def register():
    for cls in [FCD_PT_FabricationConstructionDraftsmanTools]:
        if hasattr(cls, 'bl_rna'):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass

def unregister():
    for cls in reversed([FCD_PT_FabricationConstructionDraftsmanTools]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

