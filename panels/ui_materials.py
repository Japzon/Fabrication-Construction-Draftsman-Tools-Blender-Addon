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

class LSD_PT_Materials_And_Textures:
    """
    Drawing helper for the 'Materials & Texturing' panel.
    Provides a clean, accessible interface for material management,
    smart presets, and texture painting tools.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.lsd_panel_enabled_materials

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        # --- Header ---
        box, is_expanded = ui_common.draw_panel_header(layout, context, "Materials & Textures", "lsd_show_panel_materials", "lsd_panel_enabled_materials")

        if is_expanded:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                box.label(text="Select a Mesh Object", icon='INFO')
                return
            
            # --- SECTION: MATERIAL TRANSFORM (ALWAYS AVAILABLE) ---
            tex_box = box.box()
            tex_box.label(text="Material Transform", icon='UV_DATA')
            
            col_tex = tex_box.column(align=True)
            col_tex.prop(scene, "lsd_tex_pos", text="Location")
            col_tex.prop(scene, "lsd_tex_rot", text="Rotation (Z)")
            col_tex.prop(scene, "lsd_tex_scale", text="Scale")
            
            # --- SECTION: SMART PRESETS (DROPDOWN MOD) ---
            preset_box = box.box()
            preset_box.label(text="Add Smart Material", icon='SHADING_TEXTURE')
            row = preset_box.row(align=True)
            row.prop(scene, "lsd_smart_material_type", text="")
            row.operator("lsd.material_add_smart", text="Add Layer", icon='ADD')
            
            # --- AI Editor Note: Add "New from Image" operator here ---
            preset_box.operator("lsd.material_from_image", text="New from Image File", icon='IMAGE_DATA')

            # --- SECTION: MATERIAL SLOTS ---
            row = box.row()
            row.template_list("LSD_UL_Mat_List", "", obj, "material_slots", obj, "active_material_index", rows=5)
            
            col = row.column(align=True)
            col.operator("lsd.material_add", icon='ADD', text="").mode = 'NEW'
            col.operator("object.material_slot_remove", icon='REMOVE', text="")
            col.separator()
            col.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'UP'
            col.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'DOWN'

            # --- SECTION: ASSIGNMENT TOOLS ---
            if obj.mode == 'EDIT':
                row = box.row(align=True)
                row.operator("object.material_slot_assign", text="Assign")
                row.operator("object.material_slot_select", text="Select")
                row.operator("object.material_slot_deselect", text="Deselect")

            # --- SECTION: MERGE ---
            box.operator("lsd.material_merge", text="Composite All Layers", icon='SHADING_RENDERED')

            # --- SECTION: ACTIVE MATERIAL PROPERTIES ---
            active_mat = obj.active_material
            if active_mat:
                prop_box = box.box()
                prop_box.label(text=f"Properties: {active_mat.name}", icon='MATERIAL')
                
                if active_mat.use_nodes and active_mat.node_tree:
                    nodes = active_mat.node_tree.nodes
                    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    
                    if bsdf:
                        col = prop_box.column()
                        col.prop(bsdf.inputs['Base Color'], "default_value", text="Base Color")
                        col.prop(bsdf.inputs['Metallic'], "default_value", text="Metallic", slider=True)
                        col.prop(bsdf.inputs['Roughness'], "default_value", text="Roughness", slider=True)
                        
                        col.separator()
                        # Task 3: Robust Transparency Control
                        col.prop(scene, "lsd_material_transparency", text="Transparency (Alpha)", slider=True)
                        
                        col.separator()
                        col.prop(bsdf.inputs['Emission Color'], "default_value", text="Emission")
                        col.prop(bsdf.inputs['Emission Strength'], "default_value", text="Strength")
                        
                        col.separator()
                        col.operator("lsd.material_load_texture", text="Load Texture to Color", icon='IMAGE_DATA')

                        sett_box = prop_box.box()
                        sett_box.label(text="Advanced Settings", icon='PREFERENCES')
                        sett_box.prop(active_mat, "blend_method")
                        sett_box.prop(active_mat, "shadow_method")
                    else:
                        prop_box.label(text="No Principled BSDF Node", icon='ERROR')
                else:
                    prop_box.label(text="Material does not use nodes", icon='ERROR')


            # --- SECTION: TEXTURE PAINT ---
            brush_box = box.box()
            brush_box.label(text="Texture Paint Brushes", icon='BRUSH_DATA')
            grid = brush_box.grid_flow(columns=2, align=True)
            grid.operator("lsd.paint_setup_brush", text="Dirt").brush_type = 'DIRT'
            grid.operator("lsd.paint_setup_brush", text="Scratches").brush_type = 'SCRATCH'
            grid.operator("lsd.paint_setup_brush", text="Rust").brush_type = 'RUST'
            grid.operator("lsd.paint_setup_brush", text="Oil").brush_type = 'OIL'

            # --- SECTION: UV TOOLS ---
            uv_box = box.box()
            uv_box.label(text="UV Layout Tools", icon='UV')
            grid = uv_box.grid_flow(columns=2, align=True)
            grid.operator("lsd.uv_smart_unwrap", text="Smart Project").method = 'SMART'
            grid.operator("lsd.uv_smart_unwrap", text="Cube Project").method = 'CUBE'
            grid.operator("lsd.uv_smart_unwrap", text="Cylinder Project").method = 'CYLINDER'
            grid.operator("lsd.uv_smart_unwrap", text="Sphere Project").method = 'SPHERE'
            
            row = uv_box.row()
            row.operator("lsd.uv_smart_unwrap", text="Standard Unwrap (Use Seams)").method = 'UNWRAP'


def register():
    for cls in [LSD_PT_Materials_And_Textures]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([LSD_PT_Materials_And_Textures]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

