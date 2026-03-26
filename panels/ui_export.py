# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
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

class URDF_PT_ImportExportSystem:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Export System' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.urdf_panel_enabled_export

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        # AI Editor Note: The panel header now uses a dedicated operator to toggle
        # its expanded state. This prevents unintended expansions on hover,
        # ensuring the update logic (like auto-collapse) only runs on explicit clicks.
        # The `prop` is still used for the visual toggle icon.
        is_expanded = scene.urdf_show_panel_export
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Import/Export System", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_export"
        row.prop(scene, "urdf_show_panel_export", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_export"


        if is_expanded:
            
            
            # --- Export System Section ---
            export_sys_box = box.box()
            export_sys_box.label(text="Export System", icon='EXPORT')
            
            # --- 1. Workspace (First in workflow) ---
            export_sys_box.label(text="1. Workspace Setup", icon='FILE_FOLDER')
            export_sys_box.operator("urdf.generate_ros2_workspace", text="Generate ROS 2 Workspace", icon='FILE_NEW')
            
            export_sys_box.separator()
            
            # --- 2. Package Settings ---
            export_sys_box.label(text="2. Package Settings", icon='PACKAGE')
            col = export_sys_box.column()
            
            # --- Export List ---
            col.label(text="Armatures to Export:")
            row = col.row()
            row.template_list("URDF_UL_ExportList", "", scene, "urdf_export_list", scene, "urdf_export_list_index", rows=3)
            col_ops = row.column(align=True)
            col_ops.operator("urdf.export_list_add", text="", icon='ADD')
            col_ops.operator("urdf.export_list_remove", text="", icon='REMOVE')
            
            col.separator()
            
            # Content Checkboxes
            col.label(text="Include in Package:")
            flow = col.grid_flow(columns=2, align=True)
            flow.prop(scene, "urdf_export_check_meshes")
            flow.prop(scene, "urdf_export_check_textures")
            flow.prop(scene, "urdf_export_check_config")
            flow.prop(scene, "urdf_export_check_launch")
            
            col.separator()
            col.prop(scene, "urdf_export_mesh_format")
            
            # --- 3. Export Action ---
            export_sys_box.separator()
            export_sys_box.label(text="3. Export", icon='EXPORT')
            row = export_sys_box.row()
            row.scale_y = 1.5
            row.operator("urdf.export_general", text="Export Package")
            
            # Tools
            export_sys_box.separator()
            export_sys_box.operator("urdf.export_gazebo_world", text="Export Gazebo World", icon='WORLD')
            
            # --- 4. Quick Export Selected ---
            export_sys_box.separator()
            export_sys_box.label(text="4. Quick Export (Selected)", icon='EXPORT')
            row = export_sys_box.row(align=True)
            row.prop(scene, "urdf_quick_export_format", text="")
            row.operator("urdf.export_selected", text="Export Mesh", icon='SCENE_DATA')


def register():
    for cls in [URDF_PT_ImportExportSystem]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_ImportExportSystem]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

