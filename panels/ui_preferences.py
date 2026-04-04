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

class LSD_PT_Preferences:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Preferences' panel. It is not a
    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Preferences panel is always available if the main panel is.
        return True

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Preferences panel.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Preferences", 
            "lsd_show_panel_preferences", 
            "lsd_panel_enabled_preferences"
        )
        
        if is_expanded:
            # --- Viewport Display Settings ---
            display_box = box.box()
            display_box.label(text="Viewport Display", icon='VIEW3D')
            row = display_box.row(align=True)
            row.prop(scene, "lsd_viz_gizmos", text="Show Gizmos")
            row.prop(scene, "lsd_show_bones", text="Show Bones")

            # --- Scene Units ---
            units_box = box.box()
            units_box.label(text="Scene Units", icon='SCENE_DATA')
            
            unit_settings = scene.unit_settings
            col = units_box.column(align=True)
            col.prop(unit_settings, "system", text="System")
            
            if unit_settings.system != 'NONE':
                col.prop(unit_settings, "scale_length", text="Unit Scale")
                col.prop(unit_settings, "length_unit", text="Measurement Unit")
                col.prop(unit_settings, "use_separate", text="Separate Units")

            # --- UI Behavior ---
            behavior_box = box.box()
            behavior_box.label(text="UI Behavior", icon='PREFERENCES')
            behavior_box.prop(scene, "lsd_auto_collapse_panels")

            # --- Panel Order & Visibility Data ---
            names = {
                "lsd_order_ai_factory": "Generate",
                "lsd_order_assets": "Asset Library",
                "lsd_order_parts": "Mechanical Presets",
                "lsd_order_architectural": "Architectural Presets",
                "lsd_order_vehicle": "Vehicle Presets",
                "lsd_order_electronics": "Electronic Presets",
                "lsd_order_dimensions": "Dimensions & Precision Transforms",
                "lsd_order_procedural": "Procedural Toolkit",
                "lsd_order_kinematics": "Kinematics Setup",
                "lsd_order_physics": "Physics",
                "lsd_order_transmission": "Transmission",
                "lsd_order_materials": "Materials & Textures",
                "lsd_order_lighting": "Environment & Lighting",
                "lsd_order_camera": "Camera Studio & Pathing",
                "lsd_order_export": "Export System",
                "lsd_order_preferences": "Preferences",
            }
            
            order_to_visibility = {
                "lsd_order_ai_factory": "lsd_panel_enabled_ai_factory",
                "lsd_order_parts": "lsd_panel_enabled_parts",
                "lsd_order_architectural": "lsd_panel_enabled_architectural",
                "lsd_order_vehicle": "lsd_panel_enabled_vehicle",
                "lsd_order_electronics": "lsd_panel_enabled_electronics",
                "lsd_order_procedural": "lsd_panel_enabled_procedural",
                "lsd_order_dimensions": "lsd_panel_enabled_dimensions",
                "lsd_order_materials": "lsd_panel_enabled_materials",
                "lsd_order_lighting": "lsd_panel_enabled_lighting",
                "lsd_order_camera": "lsd_panel_enabled_camera",
                "lsd_order_kinematics": "lsd_panel_enabled_kinematics",
                "lsd_order_physics": "lsd_panel_enabled_physics",
                "lsd_order_transmission": "lsd_panel_enabled_transmission",
                "lsd_order_export": "lsd_panel_enabled_export",
                "lsd_order_assets": "lsd_panel_enabled_assets",
            }

            props = {k: getattr(scene, k, 0) for k in names.keys()}
            sorted_props = sorted(props.items(), key=lambda x: x[1])

            # --- Panel Visibility ---
            visibility_box = box.box()
            visibility_box.label(text="Visible Panels", icon='HIDE_OFF')
            col = visibility_box.column(align=True)
            
            for prop_name, _ in sorted_props:
                vis_prop = order_to_visibility.get(prop_name)
                if vis_prop:
                    col.prop(scene, vis_prop, text=names[prop_name])

            # --- Panel Order ---
            order_box = box.box()
            order_box.label(text="Panel Order", icon='SORTSIZE')
            
            for prop_name, _ in sorted_props:
                row = order_box.row(align=True)
                row.label(text=names[prop_name])
                op_up = row.operator("lsd.move_panel", text="", icon='TRIA_UP')
                op_up.direction = 'UP'
                op_up.prop_name = prop_name
                
                op_down = row.operator("lsd.move_panel", text="", icon='TRIA_DOWN')
                op_down.direction = 'DOWN'
                op_down.prop_name = prop_name
                
            row = order_box.row(align=True)
            row.operator("lsd.reset_panel_order", icon='LOOP_BACK', text="Reset")



def register():
    for cls in [LSD_PT_Preferences]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([LSD_PT_Preferences]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

