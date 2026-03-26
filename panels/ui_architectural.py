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

class URDF_PT_ArchitecturalPresets:
    """
    Drawing helper for the 'Architectural Presets' panel.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Check if the panel is enabled in scene properties
        return getattr(context.scene, "urdf_panel_enabled_architectural", True)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Architectural Presets drawing helper.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Architectural Presets", 
            "urdf_show_panel_architectural", 
            "urdf_panel_enabled_architectural"
        )
        
        if not is_expanded:
            return

        # 2. Main Generation Controls
        col = box.column(align=True)
        col.label(text="Select Element", icon='RESTRICT_SELECT_OFF')
        col.prop(scene, "urdf_architectural_type", text="Structural Type")
        
        gen_row = col.row(align=True)
        gen_row.scale_y = 1.2
        op = gen_row.operator("urdf.create_part", text="Generate Preset", icon='PLUS')
        op.category = 'ARCHITECTURAL'
        op.type_sub = scene.urdf_architectural_type
        
        # 3. Dynamic Edit Section for Active Architectural Part
        obj = context.active_object
        # Ensure object has the required property group and it's initialized
        if obj and hasattr(obj, "urdf_mech_props"):
            props = obj.urdf_mech_props
            
            # Explicitly check if the object belongs to this UI module
            if props.is_part and props.category == 'ARCHITECTURAL':
                box.separator()
                edit_box = box.box()
                edit_box.label(text=f"Edit {obj.name}", icon='WRENCH')
                
                # Fetch type label safely
                raw_type = str(props.type_architectural)
                type_label = raw_type.replace('_', ' ').title()
                edit_box.label(text=f"Type: {type_label}", icon='OUTLINER_OB_MESH')
                
                edit_col = edit_box.column(align=True)
                
                # Draw shared properties first
                if raw_type in {'WALL', 'WINDOW', 'DOOR', 'BEAM', 'STAIRS'}:
                    edit_col.prop(props, "length")
                if raw_type in {'WALL', 'WINDOW', 'DOOR', 'COLUMN', 'STAIRS'}:
                    edit_col.prop(props, "height")
                
                # Draw type-specific properties
                if raw_type == 'WALL':
                    edit_col.prop(props, "wall_thickness")
                elif raw_type == 'WINDOW':
                    edit_col.prop(props, "window_frame_thickness")
                    edit_col.prop(props, "glass_thickness")
                elif raw_type == 'DOOR':
                    edit_col.prop(props, "window_frame_thickness", text="Frame Thickness")
                elif raw_type == 'COLUMN':
                    edit_col.prop(props, "radius")
                elif raw_type == 'STAIRS':
                    edit_col.prop(props, "step_count")
                    edit_col.prop(props, "step_height")
                    edit_col.prop(props, "step_depth")
                
                edit_box.separator()
                edit_box.operator("urdf.bake_mesh", text="Bake to Static Mesh", icon='CHECKBOX_HLT')

def register():
    # No classes to register here as it's a helper
    pass

def unregister():
    pass
