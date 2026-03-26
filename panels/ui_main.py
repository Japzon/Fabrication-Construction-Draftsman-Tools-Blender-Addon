# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T (GPL COMPLIANT)
# This add-on is protected under the GNU General Public License (GPL) to ensure 
# fair use and free distribution. The original architecture, source code, and 
# design logic are the intellectual property of Greenlex Systems Services Incorporated. 
#
# No party is authorized to claim authorship or ownership of this original work.
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
from .ui_ai_factory import URDF_PT_Generate
from .ui_parts import URDF_PT_MechanicalPresets
from .ui_materials import URDF_PT_MaterialsAndTextures
from .ui_lighting import URDF_PT_LightingAndAtmosphere
from . import ui_electronics
from .ui_electronics import URDF_PT_ElectronicPresets
from .ui_dimensions import URDF_PT_DimensionsAndMeasuring
from .ui_parametric import URDF_PT_ParametricToolkit
from .ui_architectural import URDF_PT_ArchitecturalPresets
from .ui_inertial import URDF_PT_PhysicsInertial
from .ui_collision import URDF_PT_PhysicsCollision
from .ui_transmission import URDF_PT_Transmission
from .ui_kinematics import URDF_PT_KinematicsSetup
from .ui_assets import URDF_PT_AssetLibrarySystem
from .ui_export import URDF_PT_ImportExportSystem
from .ui_preferences import URDF_PT_Preferences

class URDF_PT_FabricationConstructionDraftsmanToolsAutomated(bpy.types.Panel):
    """
    The Master Panel that acts as a container for all other panels.
    It dynamically draws the sub-panels in the order defined by the user.
    """
    bl_label = "Fabrication & Construction Draftsman Tools (Automated)"
    bl_idname = "VIEW3D_PT_urdf_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Draftsman Tools'
    bl_order = 0
    
    def draw(self, context):
        # Define the mapping of panels to their order properties
        panel_map = [
            (URDF_PT_Generate, "urdf_order_ai_factory"),
            (URDF_PT_MechanicalPresets, "urdf_order_parts"),
            (URDF_PT_ElectronicPresets, "urdf_order_electronics"),
            (URDF_PT_ParametricToolkit, "urdf_order_parametric"),
            (URDF_PT_DimensionsAndMeasuring, "urdf_order_dimensions"),
            (URDF_PT_MaterialsAndTextures, "urdf_order_materials"),
            (URDF_PT_LightingAndAtmosphere, "urdf_order_lighting"),
            (URDF_PT_KinematicsSetup, "urdf_order_kinematics"),
            (URDF_PT_PhysicsInertial, "urdf_order_inertial"),
            (URDF_PT_PhysicsCollision, "urdf_order_collision"),
            (URDF_PT_Transmission, "urdf_order_transmission"),
            (URDF_PT_AssetLibrarySystem, "urdf_order_assets"),
            (URDF_PT_ImportExportSystem, "urdf_order_export"),
            (URDF_PT_Preferences, "urdf_order_preferences"),
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
            # Call the static draw method, passing in this panel's layout.
            # Wrapped in try/except so an error in one sub-panel never
            # prevents the panels below it from being drawn.
            try:
                panel_cls.draw(self.layout, context)
            except Exception as e:
                import traceback
                err_box = self.layout.box()
                err_box.label(text=f"Panel error: {type(e).__name__}", icon='ERROR')
                print(f"[URDF Addon] Panel draw error in {panel_cls.__name__}: {e}")
                traceback.print_exc()

# ------------------------------------------------------------------------


def register():
    for cls in [URDF_PT_FabricationConstructionDraftsmanToolsAutomated]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_FabricationConstructionDraftsmanToolsAutomated]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

