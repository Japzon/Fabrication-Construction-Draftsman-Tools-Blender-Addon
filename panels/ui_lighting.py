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

class URDF_PT_LightingAndAtmosphere:
    """
    Drawing helper for the 'Lighting & Atmosphere' panel.
    Now focused on individual light editing for Anime-style flexibility.
    """

    @staticmethod
    def poll(context: bpy.types.Context) -> bool:
        return context.scene.urdf_panel_enabled_lighting

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        props = getattr(scene, "urdf_lighting_props", None)
        
        # Master Box
        box = layout.box()
        
        # Header Row
        is_expanded = getattr(scene, "urdf_show_panel_lighting", False)
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        row.scale_y = 1.1
        
        op = row.operator("urdf.toggle_panel_visibility", text="Lighting & Atmosphere", emboss=False, icon=icon)
        if op: op.panel_property = "urdf_show_panel_lighting"
        
        row.prop(scene, "urdf_show_panel_lighting", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        if close_op: close_op.prop_name = "urdf_panel_enabled_lighting"

        if is_expanded:
            # --- GLOBAL ENVIRONMENT ---
            if props:
                ebbox = box.box()
                ebbox.label(text="Global Environment", icon='WORLD')
                
                row = ebbox.row(align=True)
                row.prop(props, "light_preset", text="Preset")
                
                grid = ebbox.grid_flow(columns=2, align=True)
                col_l = grid.column(align=True)
                col_l.prop(props, "base_color", text="Tint")
                col_l.prop(props, "background_color", text="Bg")
                
                col_r = grid.column(align=True)
                col_r.prop(props, "light_intensity", text="Power")
                
                # Global Toon Utilities
                ebbox.separator()
                row = ebbox.row(align=True)
                row.label(text="Batch Styling:", icon='LIGHT')
                op_t = row.operator("urdf.global_toon_sharpness", text="Toon-Ready Scene", icon='SHADING_SOLID')
                if op_t: op_t.mode = 'TOON'
                op_r = row.operator("urdf.global_toon_sharpness", text="Realistic Scene", icon='SHADING_RENDERED')
                if op_r: op_r.mode = 'REALISTIC'
            else:
                box.label(text="Error: Lighting Settings (props) not found.", icon='ERROR')

            # --- MATERIAL UTILITIES ---
            mbox = box.box()
            mbox.label(text="Material Utilities", icon='NODE_MATERIAL')
            mbox.operator("urdf.apply_toon_shader", text="Prepare Object for Toon Style", icon='SHADING_RENDERED')

            # --- SMART LIGHT EDITOR (INDIVIDUAL CONTROL) ---
            box.separator()
            lbox = box.box()
            lbox.label(text="Selected Light Editor", icon='LIGHT_SUN')
            
            obj = context.active_object
            if obj and obj.type == 'LIGHT' and hasattr(obj, 'data'):
                light = obj.data
                main_col = lbox.column(align=True)
                
                # Simplified Toon Setup
                main_col.operator("urdf.toonify_selected_lights", text="Toonify Selected Light", icon='SHADING_SOLID')
                
                main_col.separator()
                
                # Physical Properties (Direct Native Binding)
                if hasattr(light, 'energy'):
                    row = main_col.row(align=True)
                    row.prop(light, "type", text="Type")
                    row.prop(light, "energy", text="Power")
                
                if hasattr(light, 'color'):
                    main_col.prop(light, "color", text="Color")
                
                # Targeting (Eyedropper)
                if props:
                    main_col.separator()
                    tbox = main_col.box()
                    tbox.label(text="Targeting (Eyedropper)", icon='TRACKING')
                    tbox.prop(props, "selected_light_target", text="")
                    tbox.operator("urdf.light_target", text="Add selected lighting to track", icon='ADD')
                
                # Status Detection (Super-Safe Check)
                lbox.separator()
                lbox.label(text=f"Editing: {obj.name}", icon='INFO')
                
                is_toon = False
                soft_size = getattr(light, 'shadow_soft_size', 1.0)
                radius = getattr(light, 'radius', 1.0)
                angle = getattr(light, 'angle', 1.0)
                if soft_size == 0.0 or radius == 0.0 or angle == 0.0:
                    is_toon = True
                
                if is_toon:
                    lbox.label(text="Mode: True Constant (Toon), Sharp Shadows.", icon='CHECKBOX_HLT')
                else:
                    lbox.label(text="Mode: Realistic Gradient, Soft Shadows.", icon='CHECKBOX_DEHLT')
            else:
                lbox.label(text="Select a light source to edit.", icon='INFO')
                lbox.label(text="Tip: Use Toonify Light for sharp shadows", icon='LIGHT')

def register():
    pass

def unregister():
    pass

