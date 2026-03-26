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

class URDF_PT_KinematicsSetup:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Kinematics Setup' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @staticmethod
    def poll(context: bpy.types.Context) -> bool:
        return context.scene.urdf_panel_enabled_kinematics

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        is_expanded = scene.urdf_show_panel_kinematics
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Kinematics Setup", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_kinematics"
        row.prop(scene, "urdf_show_panel_kinematics", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_kinematics"


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
            row.operator("urdf.snap_cursor_to_active", text="To Origin")

            # AI Editor Note: Local Axis Implementation & AttributeError Fix
            # The UI now binds to a scene property. A depsgraph handler keeps this
            # property synchronized with the 3D cursor's actual position, avoiding
            # writing to data from a draw function.
            if context.active_object:
                # Draw the UI property field. When the user edits this, the update callback will run.
                cursor_box.prop(scene, "urdf_cursor_local_pos", text="Local")
            else:
                # Fallback to world coordinates if no object is active.
                cursor_box.prop(scene.cursor, "location", text="World")

            # Add a button that calls the operator to move the selected object's origin to the cursor.
            cursor_box.operator("urdf.set_origin_to_cursor", icon='OBJECT_ORIGIN')

            # --- Section: Active Robot ---
            robot_box = box.box()
            robot_box.label(text="Active Robot", icon='OUTLINER_OB_ARMATURE')
            col = robot_box.column(align=True)
            col.prop(scene, "urdf_active_rig", text="")
            row = col.row(align=True)
            # AI Editor Note: Added Visual Gizmos Dropdown Feature
            row.prop(scene, "urdf_gizmo_style", text="Gizmo Style")
            
            row = col.row(align=True)
            row.operator("urdf.create_rig", icon='ADD', text="New")
            row.operator("urdf.merge_armatures", icon='LINKED', text="Merge Armatures")

            # --- Section: Bone Tools ---
            bone_tools_box = box.box()
            bone_tools_box.label(text="Bone Tools", icon='BONE_DATA')
            col = bone_tools_box.column(align=True)
            col.prop(scene, "urdf_bone_mode", text="")
            col.prop(scene, "urdf_bone_axis", text="Align Axis")
            col.operator("urdf.add_bone", icon='BONE_DATA', text="Set / Align Bones")
            col.operator("urdf.purge_bones", icon='TRASH', text="Purge Selected Bones")
            col.operator("urdf.parent_to_active", icon='LINKED', text="Parent Selected to Active")

            if context.mode == 'OBJECT':
                bone_tools_box.operator("urdf.enter_pose_mode", icon='POSE_HLT')
            else:
                bone_tools_box.operator("urdf.enter_object_mode", icon='OBJECT_DATAMODE')

            # --- Section: Joint Editor ---
            # AI Editor Note: Now visible in Object Mode if a valid child mesh (like a generated joint) is selected.
            show_editor = False
            if context.mode == 'POSE':
                show_editor = True
            elif context.mode == 'OBJECT':
                obj = context.active_object
                rig = scene.urdf_active_rig
                if obj and rig:
                    if obj == rig:
                        show_editor = True
                    elif obj.parent == rig and obj.parent_type == 'BONE':
                        show_editor = True

            if show_editor:
                joint_editor_box = box.box()
                
                # --- AI Editor Note: Tool-based UI ---
                # The UI now reads from and writes to global tool settings stored on the scene.
                # This decouples the UI from the selection, making it more robust and solving
                # visibility and multi-object editing issues.
                tool_props = scene.urdf_joint_editor_settings
                
                # Header
                header = joint_editor_box.row(align=True)
                header.label(text="Joint Editor Tool", icon='CONSTRAINT_BONE')

                # --- Sub-section: Joint Constraints ---
                constraints_box = joint_editor_box.box()
                constraints_box.prop(tool_props, "joint_type") # Now binds to scene property
                
                if tool_props.joint_type not in ['fixed', 'none']:
                    constraints_box.prop(tool_props, "axis_enum")
                
                if tool_props.joint_type != 'none':
                    size_box = constraints_box.box()
                    row = size_box.row(align=True)
                    if tool_props.joint_type in ['revolute', 'continuous']:
                        row.prop(tool_props, "joint_radius")
                    row.prop(tool_props, "gizmo_radius")

                if tool_props.joint_type in ['revolute', 'prismatic']:
                    limits_box = constraints_box.box()
                    limits_box.label(text="Limits")
                    row = limits_box.row(align=True)
                    row.prop(tool_props, "lower_limit")
                    row.prop(tool_props, "upper_limit")

                # Joint Placement Mode
                placement_box = joint_editor_box.box()
                placement_box.label(text="Joint Placement Mode", icon='POSE_HLT')
                if hasattr(scene, "urdf_placement_mode") and scene.urdf_placement_mode:
                    placement_box.operator("urdf.toggle_placement", text="Stop Joint Placement Mode", icon='CANCEL')
                else:
                    placement_box.operator("urdf.toggle_placement", text="Start Joint Placement Mode", icon='POSE_HLT')
                
                placement_box.operator("urdf.apply_rest_pose", icon='ARMATURE_DATA', text="Apply as Rest Pose")


                # --- Sub-section: Relationships ---
                relations_box = joint_editor_box.box()
                relations_box.label(text="Relationships", icon='ACTION')

                # Gear Ratio / Mimic
                # This part still needs an active bone to determine the target for prop_search
                # This part requires an active bone and associated rig
                active_bone = context.active_pose_bone
                active_obj = context.active_object
                
                if active_bone and active_obj and active_obj.type == 'ARMATURE':
                    props = active_bone.urdf_props
                    ratio_box = relations_box.box()
                    ratio_box.label(text="Gear Ratio / Mimic", icon='CONSTRAINT')
                    if len(props.mimic_drivers) > 0:
                        lbox = ratio_box.box()
                        for i, m in enumerate(props.mimic_drivers):
                            r = lbox.row()
                            r.label(text=f"Target: {m.target_bone} (Ratio: {m.ratio:.2f})")
                            op = r.operator("urdf.remove_mimic", text="", icon='X')
                            op.index = i
                    add_box = ratio_box.box()
                    add_box.label(text="Add New Driver:")
                    row_t = add_box.row(align=True)
                    if active_obj.pose:
                        row_t.prop_search(props, "ratio_target_bone", active_obj.pose, "bones", text="Target")
                        op_t = row_t.operator("urdf.pick_bone", text="", icon='EYEDROPPER')
                        op_t.mode = 0
                        row_ref = add_box.row(align=True)
                        row_ref.prop_search(props, "ratio_ref_bone", active_obj.pose, "bones", text="Ref Bone")
                        op_r = row_ref.operator("urdf.pick_bone", text="", icon='EYEDROPPER')
                        op_r.mode = 1
                    else:
                        row_t.label(text="Select an ARM/Rig for relationships", icon='ERROR')
                    row_r = add_box.row(align=True)
                    row_r.prop(props, "ratio_value")
                    row_r.prop(props, "ratio_invert", text="Invert", toggle=True)
                    row_r.operator("urdf.calculate_ratio", text="", icon='DRIVER_DISTANCE')
                    add_box.operator("urdf.add_mimic", icon='ADD', text="Add / Update Driver")
                else:
                    # Show info if no active bone for relationships
                    relations_box.label(text="Select a bone to manage relationships.", icon='INFO')


def register():
    for cls in [URDF_PT_KinematicsSetup]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_KinematicsSetup]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)
