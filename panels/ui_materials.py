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

class URDF_PT_MaterialsAndTextures:
    """
    Drawing helper for the 'Materials & Texturing' panel.
    Provides a clean, accessible interface for material management,
    smart presets, and texture painting tools.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.urdf_panel_enabled_materials

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        is_expanded = scene.urdf_show_panel_materials
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Materials & Textures", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_materials"
        row.prop(scene, "urdf_show_panel_materials", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_materials"

        if is_expanded:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                box.label(text="Select a Mesh Object", icon='INFO')
                return
            
            # --- SECTION: MATERIAL TRANSFORM (MOVED TO TOP) ---
            active_mat = obj.active_material
            if active_mat and active_mat.use_nodes and active_mat.node_tree:
                tex_box = box.box()
                tex_box.label(text="Material Transform", icon='UV_DATA')
                
                nodes = active_mat.node_tree.nodes
                # AI Editor Note: Simplified search logic. Instead of tracing from the BSDF,
                # just find the first available Mapping node in the tree. This is more robust
                # for materials that are not set up in the standard "TexCoord->Mapping->Image->BSDF" way.
                mapping_node = next((n for n in nodes if n.type == 'MAPPING'), None)
                
                if mapping_node:
                    col_tex = tex_box.column(align=True)
                    col_tex.prop(mapping_node.inputs['Location'], "default_value", text="Location")
                    col_tex.prop(mapping_node.inputs['Rotation'], "default_value", index=2, text="Rotation")
                    col_tex.separator()
                    col_tex.prop(active_mat, "urdf_uniform_scale", slider=True)
                    col_tex.prop(mapping_node.inputs['Scale'], "default_value", text="Scale (Axis)")
                else:
                    tex_box.operator("urdf.add_mapping_nodes", icon='ADD')

            
            # --- SECTION: SMART PRESETS ---
            preset_box = box.box()
            preset_box.label(text="Add Smart Material", icon='SHADING_TEXTURE')
            grid = preset_box.grid_flow(columns=2, align=True)
            grid.operator("urdf.material_add_smart", text="Plastic").mat_type = 'PLASTIC'
            grid.operator("urdf.material_add_smart", text="Metal").mat_type = 'METAL'
            grid.operator("urdf.material_add_smart", text="Rubber").mat_type = 'RUBBER'
            grid.operator("urdf.material_add_smart", text="Glass").mat_type = 'GLASS'
            grid.operator("urdf.material_add_smart", text="Carbon Fiber").mat_type = 'CARBON'
            grid.operator("urdf.material_add_smart", text="Aluminum").mat_type = 'ALUMINUM'
            grid.operator("urdf.material_add_smart", text="3D Printed").mat_type = 'PRINTED'
            grid.operator("urdf.material_add_smart", text="Emissive").mat_type = 'EMISSIVE'
            
            # --- AI Editor Note: Add "New from Image" operator here ---
            preset_box.operator("urdf.material_from_image", text="New from Image File", icon='IMAGE_DATA')

            # --- SECTION: MATERIAL SLOTS ---
            row = box.row()
            row.template_list("URDF_UL_Mat_List", "", obj, "material_slots", obj, "active_material_index", rows=5)
            
            col = row.column(align=True)
            col.operator("urdf.material_add", icon='ADD', text="").mode = 'NEW'
            col.operator("object.material_slot_remove", icon='REMOVE', text="")
            col.separator()
            col.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'DOWN'
            col.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'UP'

            # --- SECTION: ASSIGNMENT TOOLS ---
            if obj.mode == 'EDIT':
                row = box.row(align=True)
                row.operator("object.material_slot_assign", text="Assign")
                row.operator("object.material_slot_select", text="Select")
                row.operator("object.material_slot_deselect", text="Deselect")

            # --- SECTION: MERGE ---
            box.operator("urdf.material_merge", text="Composite All Layers", icon='SHADING_RENDERED')

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
                        col.prop(bsdf.inputs['Alpha'], "default_value", text="Alpha", slider=True)
                        
                        col.separator()
                        col.prop(bsdf.inputs['Emission Color'], "default_value", text="Emission")
                        col.prop(bsdf.inputs['Emission Strength'], "default_value", text="Strength")
                        
                        col.separator()
                        col.operator("urdf.material_load_texture", text="Load Texture to Color", icon='IMAGE_DATA')

                        sett_box = prop_box.box()
                        sett_box.label(text="Settings", icon='PREFERENCES')
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
            grid.operator("urdf.paint_setup_brush", text="Dirt").brush_type = 'DIRT'
            grid.operator("urdf.paint_setup_brush", text="Scratches").brush_type = 'SCRATCH'
            grid.operator("urdf.paint_setup_brush", text="Rust").brush_type = 'RUST'
            grid.operator("urdf.paint_setup_brush", text="Oil").brush_type = 'OIL'

            # --- SECTION: UV TOOLS ---
            uv_box = box.box()
            uv_box.label(text="UV Layout Tools", icon='UV')
            grid = uv_box.grid_flow(columns=2, align=True)
            grid.operator("urdf.uv_smart_unwrap", text="Smart Project").method = 'SMART'
            grid.operator("urdf.uv_smart_unwrap", text="Cube Project").method = 'CUBE'
            grid.operator("urdf.uv_smart_unwrap", text="Cylinder Project").method = 'CYLINDER'
            grid.operator("urdf.uv_smart_unwrap", text="Sphere Project").method = 'SPHERE'
            
            row = uv_box.row()
            row.operator("urdf.uv_smart_unwrap", text="Standard Unwrap (Use Seams)").method = 'UNWRAP'


def register():
    for cls in [URDF_PT_MaterialsAndTextures]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_MaterialsAndTextures]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

