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

class LSD_PT_Lighting_And_Atmosphere:
    """
    Drawing helper for the 'Lighting & Atmosphere' panel.
    Now focused on individual light editing for Anime-style flexibility.
    """

    @staticmethod
    def poll(context: bpy.types.Context) -> bool:
        return context.scene.lsd_panel_enabled_lighting

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        props = getattr(scene, "lsd_pg_lighting_props", None)
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Lighting & Atmosphere", 
            "lsd_show_panel_lighting", 
            "lsd_panel_enabled_lighting"
        )
        
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
                op_t = row.operator("lsd.global_toon_sharpness", text="Toon-Ready Scene", icon='SHADING_SOLID')
                if op_t: op_t.mode = 'TOON'
                op_r = row.operator("lsd.global_toon_sharpness", text="Realistic Scene", icon='SHADING_RENDERED')
                if op_r: op_r.mode = 'REALISTIC'
            else:
                box.label(text="Error: Lighting Settings (props) not found.", icon='ERROR')

            # --- MATERIAL UTILITIES ---
            mbox = box.box()
            mbox.label(text="Material Utilities", icon='NODE_MATERIAL')
            mbox.operator("lsd.apply_toon_shader", text="Prepare Object for Toon Style", icon='SHADING_RENDERED')

            # --- SMART LIGHT EDITOR (INDIVIDUAL CONTROL) ---
            box.separator()
            lbox = box.box()
            lbox.label(text="Selected Light Editor", icon='LIGHT_SUN')
            
            obj = context.active_object
            if obj and obj.type == 'LIGHT' and hasattr(obj, 'data'):
                light = obj.data
                main_col = lbox.column(align=True)
                
                # Simplified Toon Setup
                main_col.operator("lsd.toonify_selected_lights", text="Toonify Selected Light", icon='SHADING_SOLID')
                
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
                    tbox.operator("lsd.light_target", text="Add selected lighting to track", icon='ADD')
                
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

