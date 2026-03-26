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

    @staticmethod
    def draw(layout, context):
        scene = context.scene
        
        # --- Header Section ---
        box, is_expanded = ui_common.draw_panel_header(layout, context, "Architectural Presets", "urdf_show_panel_architectural", "urdf_panel_enabled_architectural")
        
        if not is_expanded:
            return

        # --- Selection Section ---
        sel_box = layout.box()
        sel_box.label(text="Select Element", icon='RESTRICT_SELECT_OFF')
        sel_box.prop(scene, "urdf_architectural_type", text="Structural Type")
        
        # --- Generation Trigger ---
        gen_row = sel_box.row(align=True)
        gen_row.scale_y = 1.2
        op = gen_row.operator("urdf.create_part", text="Generate Preset", icon='PLUS')
        op.category = 'ARCHITECTURAL'
        op.type_sub = scene.urdf_architectural_type
        
        # --- Property Editing Section (Active Object) ---
        obj = context.active_object
        if obj and hasattr(obj, "urdf_mech_props") and obj.urdf_mech_props.is_part:
            props = obj.urdf_mech_props
            if props.category == 'ARCHITECTURAL':
                edit_box = layout.box()
                edit_box.label(text=f"Edit {obj.name}", icon='WRENCH')
                
                # Show specific properties based on type
                if props.type_architectural == 'WALL':
                    edit_box.prop(props, "length")
                    edit_box.prop(props, "height")
                    edit_box.prop(props, "wall_thickness")
                elif props.type_architectural == 'WINDOW':
                    edit_box.prop(props, "length", text="Width")
                    edit_box.prop(props, "height")
                    edit_box.prop(props, "window_frame_thickness")
                    edit_box.prop(props, "glass_thickness")
                elif props.type_architectural == 'DOOR':
                    edit_box.prop(props, "length", text="Width")
                    edit_box.prop(props, "height")
                    edit_box.prop(props, "window_frame_thickness", text="Frame Thickness")
                elif props.type_architectural == 'COLUMN':
                    edit_box.prop(props, "radius")
                    edit_box.prop(props, "height")
                elif props.type_architectural == 'BEAM':
                    edit_box.prop(props, "length")
                    edit_box.prop(props, "width")
                    edit_box.prop(props, "height")
                elif props.type_architectural == 'STAIRS':
                    edit_box.prop(props, "length", text="Stair Width")
                    edit_box.prop(props, "step_count")
                    edit_box.prop(props, "step_height")
                    edit_box.prop(props, "step_depth")

                # Bake Button
                layout.separator()
                layout.operator("urdf.bake_mesh", text="Bake Architectural Mesh", icon='CHECKMARK')

def register():
    # No classes to register here as it's a helper
    pass

def unregister():
    pass
