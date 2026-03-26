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

class URDF_PT_Preferences:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Preferences' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Preferences panel is always available if the main panel is.
        return True

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        is_expanded = scene.urdf_show_panel_preferences
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Preferences", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_preferences"
        row.prop(scene, "urdf_show_panel_preferences", text="", emboss=False, toggle=True)


        if is_expanded:
            # --- Viewport Display Settings ---
            # AI Editor Note: Moved from standalone panel to Preferences for better organization.
            # This places global display toggles at the top of the preferences for quick access.
            display_box = box.box()
            display_box.label(text="Viewport Display", icon='VIEW3D')
            row = display_box.row(align=True)
            row.prop(scene, "urdf_viz_gizmos", text="Show Gizmos")
            row.prop(scene, "urdf_show_bones", text="Show Bones")

            # --- Scene Units ---
            # AI Editor Note: Added to provide quick access to unit settings for URDF scaling.
            # Allows setting Meters, Millimeters, Feet, Inches, etc. natively.
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
            behavior_box.prop(scene, "urdf_auto_collapse_panels")

            # --- Panel Order & Visibility Data ---
            # AI Editor Note: Define mappings to synchronize order and visibility lists.
            names = {
                "urdf_order_ai_factory": "Generate",
                "urdf_order_assets": "Asset Library",
                "urdf_order_parts": "Mechanical Presets",
                "urdf_order_electronics": "Electronic Presets",
                "urdf_order_dimensions": "Dimensions & Measuring",
                "urdf_order_parametric": "Parametric Toolkit",
                "urdf_order_kinematics": "Kinematics Setup",
                "urdf_order_inertial": "Inertial",
                "urdf_order_collision": "Collision",
                "urdf_order_transmission": "Transmission",
                "urdf_order_materials": "Materials & Textures",
                "urdf_order_lighting": "Environment & Lighting",
                "urdf_order_export": "Export System",
                "urdf_order_preferences": "Preferences",
            }
            
            # Mapping from order property to visibility property (Preferences has no visibility toggle)
            order_to_visibility = {
                "urdf_order_ai_factory": "urdf_panel_enabled_ai_factory",
                "urdf_order_parts": "urdf_panel_enabled_parts",
                "urdf_order_electronics": "urdf_panel_enabled_electronics",
                "urdf_order_parametric": "urdf_panel_enabled_parametric",
                "urdf_order_dimensions": "urdf_panel_enabled_dimensions",
                "urdf_order_materials": "urdf_panel_enabled_materials",
                "urdf_order_lighting": "urdf_panel_enabled_lighting",
                "urdf_order_kinematics": "urdf_panel_enabled_kinematics",
                "urdf_order_inertial": "urdf_panel_enabled_inertial",
                "urdf_order_collision": "urdf_panel_enabled_collision",
                "urdf_order_transmission": "urdf_panel_enabled_transmission",
                "urdf_order_export": "urdf_panel_enabled_export",
                "urdf_order_assets": "urdf_panel_enabled_assets",
            }

            props = {k: getattr(scene, k, 0) for k in names.keys()}
            sorted_props = sorted(props.items(), key=lambda x: x[1])

            # --- Panel Visibility ---
            visibility_box = box.box()
            visibility_box.label(text="Visible Panels", icon='HIDE_OFF')
            col = visibility_box.column(align=True)
            
            # AI Editor Note: Draw visibility toggles in the user-defined order.
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
                op_up = row.operator("urdf.move_panel", text="", icon='TRIA_UP')
                op_up.direction = 'UP'
                op_up.prop_name = prop_name
                
                op_down = row.operator("urdf.move_panel", text="", icon='TRIA_DOWN')
                op_down.direction = 'DOWN'
                op_down.prop_name = prop_name
                
            row = order_box.row(align=True)
            row.operator("urdf.reset_panel_order", icon='LOOP_BACK', text="Reset")



def register():
    for cls in [URDF_PT_Preferences]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_Preferences]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

