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

class LSD_UL_Mimic_Driver_List(bpy.types.UIList):

    """Listing for joint relationship drivers."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:

            row = layout.row(align=True)
            row.label(text=item.target_bone, icon='BONE_DATA')
            row.prop(item, "ratio", text="Ratio", emboss=False if index == getattr(active_data, active_propname) else True)
            # Removal uses the operator
            op = row.operator("lsd.remove_mimic", text="", icon='X', emboss=False)
            op.index = index

        elif self.layout_type == 'GRID':

            layout.alignment = 'CENTER'
            layout.label(text="", icon='CONSTRAINT')

class LSD_PT_Kinematics_Setup:

    """
    AI Editor Note:
    This class is a drawing helper for the 'Kinematics Setup' panel. It is not a
    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """
    @staticmethod
    def poll(context: bpy.types.Context) -> bool:

        return context.scene.lsd_panel_enabled_kinematics

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:

        scene = context.scene

        

        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Kinematics Setup", 
            "lsd_show_panel_kinematics", 
            "lsd_panel_enabled_kinematics"
        )

        

        if is_expanded:

            # --- AI Editor Note: New Cursor & Origin Tools ---
            # This section provides quick access to 3D cursor placement and setting object origins,
            # which are common and essential tasks when setting up kinematic chains and pivot points.
            cursor_box = box.box()
            cursor_box.label(text="Cursor & Origin Tools", icon='CURSOR')
            # AI Editor Note: Adding "Snap Cursor to Selected" and fixing the mislabeled "Snap Cursor to Origin".
            # AI Editor Note: Swapped positions of "To Selected" and "To Origin" per user request.
            row = cursor_box.row(align=True)
            row.operator("view3d.snap_cursor_to_selected", text="To Selected")
            row.operator("lsd.snap_cursor_to_active", text="To Origin")
            # AI Editor Note: Local Axis Implementation & AttributeError Fix
            # The UI now binds to a scene property. A depsgraph handler keeps this
            # property synchronized with the 3D cursor's actual position, avoiding
            # writing to data from a draw function.
            if context.active_object:

                # Draw the UI property field. When the user edits this, the update callback will run.
                cursor_box.prop(scene, "lsd_cursor_local_pos", text="Local")

            else:

                # Fallback to world coordinates if no object is active.
                cursor_box.prop(scene.cursor, "location", text="World")

            # Add a button that calls the operator to move the selected object's origin to the cursor.
            cursor_box.operator("lsd.set_origin_to_cursor", icon='OBJECT_ORIGIN')
            # --- Section: Active Robot ---
            robot_box = box.box()
            robot_box.label(text="Active Robot", icon='OUTLINER_OB_ARMATURE')
            col = robot_box.column(align=True)
            col.prop(scene, "lsd_active_rig", text="")

            

            row = col.row(align=True)
            row.operator("lsd.create_rig", icon='ADD', text="New")
            row.operator("lsd.merge_armatures", icon='LINKED', text="Merge Armatures")
            # --- Section: Bone Tools ---
            bone_tools_box = box.box()
            bone_tools_box.label(text="Bone Tools", icon='BONE_DATA')
            col = bone_tools_box.column(align=True)
            col.prop(scene, "lsd_bone_mode", text="")
            col.prop(scene, "lsd_bone_axis", text="Align Axis")
            col.operator("lsd.add_bone", icon='BONE_DATA', text="Set / Align Bones")
            col.operator("lsd.purge_bones", icon='TRASH', text="Purge Selected Bones")
            col.operator("lsd.parent_to_active", icon='LINKED', text="Parent Selected to Active")
            if context.mode == 'OBJECT':

                bone_tools_box.operator("lsd.enter_pose_mode", icon='POSE_HLT')

            else:

                bone_tools_box.operator("lsd.enter_object_mode", icon='OBJECT_DATAMODE')

            # --- Section: Joint Editor ---
            # AI Editor Note: Now visible in Object Mode if a valid child mesh (like a generated joint) is selected.
            show_editor = False
            if context.mode == 'POSE':

                show_editor = True

            elif context.mode == 'OBJECT':

                obj = context.active_object
                rig = scene.lsd_active_rig
                if obj and rig:

                    if obj == rig:

                        show_editor = True

                    elif obj.parent == rig and obj.parent_type == 'BONE':

                        show_editor = True

            if show_editor:

                joint_editor_box = box.box()

                

                # --- AI Editor Note: Direct Property UI ---
                # The UI now reads and writes directly to the active bone's kinematic properties.
                # This ensures that joint settings are persistent and unique to each individual joint.
                active_bone = context.active_pose_bone
                
                # Support Object Mode selection via parent relationship
                if not active_bone and context.active_object and context.active_object.parent_type == 'BONE':
                    active_bone = context.active_object.parent.pose.bones.get(context.active_object.parent_bone)
                
                if active_bone:
                    props = active_bone.lsd_pg_kinematic_props
                    
                    # Header
                    header = joint_editor_box.row(align=True)
                    header.label(text="Joint Editor Tool", icon='CONSTRAINT_BONE')
                    
                    # --- Joint Constraints ---
                    col = joint_editor_box.column(align=True)
                    col.prop(props, "joint_type")
                    
                    if props.joint_type not in ['fixed', 'none']:
                        col.prop(props, "axis_alignment")
                    
                    if props.joint_type != 'none':
                        row = col.row(align=True)
                        row.prop(props, "joint_radius")
                        row.prop(props, "visual_gizmo_scale")
                        
                        if props.joint_type in ['revolute', 'prismatic', 'spherical']:
                            row = col.row(align=True)
                            row.prop(props, "lower_limit")
                            row.prop(props, "upper_limit")
                else:
                    joint_editor_box.label(text="No joint selected.", icon='INFO')

                joint_editor_box.separator()
                
                # --- Joint Placement Mode ---
                col = joint_editor_box.column(align=True)
                col.label(text="Joint Placement Mode", icon='POSE_HLT')
                if hasattr(scene, "lsd_placement_mode") and scene.lsd_placement_mode:
                    col.operator("lsd.toggle_placement", text="Stop Joint Placement Mode", icon='CANCEL')
                else:
                    col.operator("lsd.toggle_placement", text="Start Joint Placement Mode", icon='POSE_HLT')
                
                col.operator("lsd.apply_rest_pose", icon='ARMATURE_DATA', text="Apply as Rest Pose")
                
                # --- Relationships ---
                relations_box = joint_editor_box.column(align=True)
                relations_box.separator()
                relations_box.label(text="Relationships", icon='ACTION')
                
                # Gear Ratio / Mimic
                active_bone = context.active_pose_bone
                active_obj = context.active_object
                
                if active_bone and active_obj and active_obj.type == 'ARMATURE':
                    props = active_bone.lsd_pg_kinematic_props
                    
                    # Sub-panel for Drivers/Gear Ratios
                    driver_box = relations_box.box()
                    driver_box.label(text="Drivers / Gear Ratios", icon='DRIVER')
                    
                    # LIST: Existing mimic drivers (if any)
                    if len(props.mimic_drivers) > 0:
                        driver_box.template_list("LSD_UL_Mimic_Driver_List", "", props, "mimic_drivers", props, "mimic_drivers_index", rows=3)
                        driver_box.separator()

                    # FORM: "Add New" section
                    driver_box.label(text="Establish New Coupling:", icon='ADD')
                    
                    if active_obj.pose:
                        row_t = driver_box.row(align=True)
                        row_t.prop_search(props, "ratio_target_bone", active_obj.pose, "bones", text="Target")
                        op_t = row_t.operator("lsd.pick_bone", text="", icon='EYEDROPPER')
                        op_t.mode = 0

                        row_ref = driver_box.row(align=True)
                        row_ref.prop_search(props, "ratio_ref_bone", active_obj.pose, "bones", text="Ref Bone")
                        op_r = row_ref.operator("lsd.pick_bone", text="", icon='EYEDROPPER')
                        op_r.mode = 1

                    else:
                        driver_box.label(text="Select an ARM/Rig for relationships", icon='ERROR')

                    row_r = driver_box.row(align=True)
                    row_r.prop(props, "ratio_value")
                    row_r.prop(props, "ratio_invert", text="Invert", toggle=True)
                    row_r.operator("lsd.calculate_ratio", text="", icon='DRIVER_DISTANCE')
                    driver_box.operator("lsd.add_mimic", icon='ADD', text="Add / Update Driver")

                else:
                    # Show info if no active bone for relationships
                    relations_box.label(text="Select a bone to manage relationships.", icon='INFO')

def register():

    for cls in [LSD_UL_Mimic_Driver_List, LSD_PT_Kinematics_Setup]:

        if hasattr(cls, 'bl_rna'):

            bpy.utils.register_class(cls)

def unregister():

    for cls in reversed([LSD_UL_Mimic_Driver_List, LSD_PT_Kinematics_Setup]):

        if hasattr(cls, 'bl_rna'):

            bpy.utils.unregister_class(cls)
