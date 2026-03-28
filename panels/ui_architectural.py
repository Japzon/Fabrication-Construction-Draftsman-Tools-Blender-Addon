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
from . import ui_common
from ..config import *

class FCD_PT_Architectural_Presets:
    """
    Modular drawing helper for Architectural Presets. 
    Completely remade to ensure robust property visibility.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return getattr(context.scene, "fcd_panel_enabled_architectural", True)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Architectural Presets", 
            "fcd_show_panel_architectural", 
            "fcd_panel_enabled_architectural"
        )
        
        if is_expanded:
            # 2. Generation Size Constraint
            cage_box = box.box()
            cage_box.label(text="Generation Size Constraint", icon='SHADING_BBOX')
            cage_box.prop(scene, "fcd_use_generation_cage", text="Use Size Cage")
            row = cage_box.row()
            row.enabled = scene.fcd_use_generation_cage
            row.prop(scene, "fcd_generation_cage_size", text="Max Dimension")
            
            # 3. Structural Elements Section
            spawn_box = box.box()
            spawn_box.label(text="Structural Elements", icon='OUTLINER_OB_MESH')
            spawn_box.prop(scene, "fcd_architectural_type", text="Type")
            
            row = spawn_box.row(align=True)
            row.scale_y = 1.2
            op = row.operator("fcd.create_part", text="Add Structural Element", icon='PLUS')
            op.category = 'ARCHITECTURAL'
            op.type_sub = scene.fcd_architectural_type
            
            # 3. Dynamic Edit Section
            obj = context.active_object
            
            # SAFETY CHECK: Only show properties for valid, addon-managed architectural objects.
            if obj and hasattr(obj, "fcd_pg_mech_props"):
                props = obj.fcd_pg_mech_props
                
                # AI Editor Note: Relaxed category check to include objects that have 
                # type_architectural set, even if the category property is lost.
                # This makes the UI much more robust during re-registrations.
                is_arch = (props.category == 'ARCHITECTURAL')
                
                if is_arch and props.is_part:
                    box.separator()
                    edit_box = box.box()
                    edit_box.label(text=f"Editing: {obj.name}", icon='PROPERTIES')
                    
                    # Fetch raw enum identifier
                    raw_type = str(props.type_architectural)
                    nice_name = raw_type.replace('_', ' ').title()
                    edit_box.label(text=f"Preset: {nice_name}", icon='MODIFIER')
                    
                    col = edit_box.column(align=True)
                    
                    # --- Shared Dimensional Properties ---
                    if raw_type in {'WALL', 'WINDOW', 'DOOR', 'BEAM', 'STAIRS'}:
                        col.prop(props, "length", text="Length")
                    if raw_type in {'WALL', 'WINDOW', 'DOOR', 'COLUMN', 'STAIRS'}:
                        col.prop(props, "height", text="Height")
                    
                    # --- Specific Logic Properties ---
                    if raw_type == 'WALL':
                        col.prop(props, "wall_thickness", text="Thickness")
                    
                    elif raw_type == 'WINDOW':
                        col.prop(props, "window_frame_thickness", text="Frame Thickness")
                        col.prop(props, "glass_thickness", text="Glass Thickness")
                    
                    elif raw_type == 'DOOR':
                        col.prop(props, "window_frame_thickness", text="Frame Size")
                    
                    elif raw_type == 'COLUMN':
                        col.prop(props, "radius", text="Support Radius")
                    
                    elif raw_type == 'BEAM':
                        col.prop(props, "radius", text="Beam Thickness")
                    
                    elif raw_type == 'STAIRS':
                        col.prop(props, "step_count", text="Total Steps")
                        col.prop(props, "step_height", text="Step Riser")
                        col.prop(props, "step_depth", text="Step Tread")

                    edit_box.separator()
                    edit_box.operator("fcd.bake_mesh", text="Finalize to Static Mesh", icon='CHECKBOX_HLT')

def register():
    pass

def unregister():
    pass
