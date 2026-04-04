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

class LSD_UL_ExportList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "rig", text="", emboss=False, icon='OUTLINER_OB_ARMATURE')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class LSD_PT_Import_Export_System:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Export System' panel. It is not a
    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.lsd_panel_enabled_export

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Import/Export System", 
            "lsd_show_panel_export", 
            "lsd_panel_enabled_export"
        )
        
        if is_expanded:
            
            
            # --- Export System Section ---
            export_sys_box = box.box()
            export_sys_box.label(text="Export System", icon='EXPORT')
            
            # --- 1. Workspace (First in workflow) ---
            export_sys_box.label(text="1. Workspace Setup", icon='FILE_FOLDER')
            export_sys_box.operator("lsd.generate_ros2_workspace", text="Generate ROS 2 Workspace", icon='FILE_NEW')
            
            export_sys_box.separator()
            
            # --- 2. Package Settings ---
            export_sys_box.label(text="2. Package Settings", icon='PACKAGE')
            col = export_sys_box.column()
            
            # --- Export List ---
            col.label(text="Armatures to Export:")
            row = col.row()
            row.template_list("LSD_UL_ExportList", "", scene, "lsd_export_list", scene, "lsd_export_list_index", rows=3)
            col_ops = row.column(align=True)
            col_ops.operator("lsd.export_list_add", text="", icon='ADD')
            col_ops.operator("lsd.export_list_remove", text="", icon='REMOVE')
            
            col.separator()
            
            # Content Checkboxes
            col.label(text="Include in Package:")
            flow = col.grid_flow(columns=2, align=True)
            flow.prop(scene, "lsd_export_check_meshes")
            flow.prop(scene, "lsd_export_check_textures")
            flow.prop(scene, "lsd_export_check_config")
            flow.prop(scene, "lsd_export_check_launch")
            
            col.separator()
            col.prop(scene, "lsd_export_mesh_format")
            
            # --- 3. Export Action ---
            export_sys_box.separator()
            export_sys_box.label(text="3. Export", icon='EXPORT')
            row = export_sys_box.row()
            row.scale_y = 1.5
            row.operator("lsd.export_general", text="Export Package")
            
            # Tools
            export_sys_box.separator()
            export_sys_box.operator("lsd.export_gazebo_world", text="Export Gazebo World", icon='WORLD')
            
            # --- 4. Quick Export Selected ---
            export_sys_box.separator()
            export_sys_box.label(text="4. Quick Export (Selected)", icon='EXPORT')
            row = export_sys_box.row(align=True)
            row.prop(scene, "lsd_quick_export_format", text="")
            row.operator("lsd.export_selected", text="Export Mesh", icon='SCENE_DATA')


def register():
    for cls in [LSD_UL_ExportList, LSD_PT_Import_Export_System]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([LSD_UL_ExportList, LSD_PT_Import_Export_System]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

