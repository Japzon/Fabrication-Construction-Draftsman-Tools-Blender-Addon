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
from .. import config
from ..config import *
from .. import core
from .. import properties
from .. import operators
from . import ui_common

class LSD_PT_Physics:
    """
    AI Editor Note:
    This class is a drawing helper for the unified 'Physics' panel (Collision & Inertial).
    It is not a registered bpy.types.Panel, but is called by the main 
    LSD_PT_FabricationConstructionDraftsmanToolsAutomated to draw its content.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.lsd_panel_enabled_physics

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Physics", 
            "lsd_show_panel_physics", 
            "lsd_panel_enabled_physics"
        )
        
        if is_expanded:
            obj = context.active_object
            source_obj = obj
            
            # 1. Identify context (Source vs Collision Mesh)
            is_collision_mesh = obj and obj.name.startswith("COLL_")
            if is_collision_mesh and obj.parent:
                source_obj = obj.parent

            # --- COLLISION SECTION ---
            cbox = box.box()
            cbox.label(text="Collision Geometry", icon='PHYSICS')
            
            if is_collision_mesh:
                cbox.label(text=f"Editing: {obj.name}", icon='EDITMODE_HLT')
            
            # 1. Primary Action
            cbox.operator("lsd.generate_collision_mesh", text="Sync/Generate Collision", icon='MESH_ICOSPHERE')
            
            # 2. Polygon Simplification Control (Selection Dependent)
            if source_obj and hasattr(source_obj, "lsd_pg_mech_props"):
                props = source_obj.lsd_pg_mech_props.collision
                # Manual Simplification & Shelling
                col = cbox.column(align=True)
                col.prop(props, "decimate_ratio", text="Poly Reduction", slider=True)
                col.prop(props, "thickness", text="Thickness/Offset")
            else:
                cbox.label(text="Select a Part or Collision Mesh", icon='INFO')
            
            # 3. Global Visibility & Cleanup (Always Visible)
            cbox.separator()
            grid = cbox.grid_flow(columns=1, align=True)
            grid.prop(context.scene, "lsd_show_collisions", text="Show All Collision Meshes", icon='HIDE_OFF')
            grid.operator("lsd.purge_collision", text="Purge Collision for Selected", icon='TRASH')

            cbox.separator()

            # --- INERTIAL SECTION ---
            ibox = box.box()
            ibox.label(text="Inertial Properties", icon='NODE_COMPOSITING')
            
            # Determine the property owner
            props_owner = None
            if context.mode == 'POSE' and context.active_pose_bone:
                props_owner = context.active_pose_bone.lsd_pg_kinematic_props
            elif source_obj and hasattr(source_obj, "lsd_pg_mech_props"):
                props_owner = source_obj.lsd_pg_mech_props
            if props_owner:
                inertial_props = props_owner.inertial
                
                # Element Selection Presets
                ibox.label(text="Solid Element Presets", icon='STRANDS')
                col = ibox.column(align=True)
                col.prop(inertial_props, "element_category")
                col.prop(inertial_props, "element_type", text="Element")
                
                ibox.separator()
                
                # Custom Mass (g/cm³) - Manual Override
                ibox.prop(inertial_props, "custom_mass_gcm3")
                
                # 1-Click Execution (Replaces multiple individual calculation buttons)
                ibox.operator("lsd.calculate_all_physics", text="Auto-Calculate Physics", icon='AUTO')
                
                ibox.separator()
                
                # Visible Properties
                col = ibox.column(align=True)
                col.prop(inertial_props, "mass")
                col.prop(inertial_props, "center_of_mass")
                
                tensor_box = ibox.box()
                tensor_box.label(text="Inertia Tensor Matrix (kg·m²)", icon='STRANDS')
                
                # 3x3 Matrix Layout
                main_col = tensor_box.column(align=True)
                
                # Top Row: Ixx, Ixy, Ixz
                row1 = main_col.row(align=True)
                row1.prop(inertial_props, "ixx", text="Ixx")
                row1.prop(inertial_props, "ixy", text="Ixy")
                row1.prop(inertial_props, "ixz", text="Ixz")
                
                # Middle Row: Iyx, Iyy, Iyz (Iyx mirrored to Ixy)
                row2 = main_col.row(align=True)
                row2.prop(inertial_props, "ixy", text="Iyx")
                row2.prop(inertial_props, "iyy", text="Iyy")
                row2.prop(inertial_props, "iyz", text="Iyz")
                
                # Bottom Row: Izx, Izy, Izz (Izx->Ixz, Izy->Iyz)
                row3 = main_col.row(align=True)
                row3.prop(inertial_props, "ixz", text="Izx")
                row3.prop(inertial_props, "iyz", text="Izy")
                row3.prop(inertial_props, "izz", text="Izz")
            else:
                ibox.label(text="Selection must have physics data", icon='INFO')


def register():
    pass

def unregister():
    pass
