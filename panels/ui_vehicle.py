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
from . import ui_common

class FCD_PT_Vehicle_Presets:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Vehicle Presets' panel. It is not a
    registered bpy.types.Panel, but is called by the main FCD_PT_FabricationConstructionDraftsmanTools
    to draw its content. This structure allows for dynamic reordering of panels.
    """
    
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.fcd_panel_enabled_vehicle

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Vehicle Presets drawing helper.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Vehicle Presets", 
            "fcd_show_panel_vehicle", 
            "fcd_panel_enabled_vehicle"
        )
        
        if is_expanded:
            # 2. Generation Size Constraint
            cage_box = box.box()
            cage_box.label(text="Generation Size Constraint", icon='SHADING_BBOX')
            cage_box.prop(scene, "fcd_use_generation_cage", text="Use Size Cage")
            row = cage_box.row()
            row.enabled = scene.fcd_use_generation_cage
            row.prop(scene, "fcd_generation_cage_size", text="Max Dimension")
            
            # 3. Preset Selection
            sel_box = box.box()
            sel_box.label(text="Choose Template", icon='RESTRICT_SELECT_OFF')
            sel_box.prop(scene, "fcd_vehicle_type", text="Type")
            
            gen_row = sel_box.row(align=True)
            gen_row.scale_y = 1.2
            # Use a more stable icon for spawning
            op = gen_row.operator("fcd.create_part", text="Spawn Vehicle", icon='PLAY')
            op.category = 'VEHICLE'
            op.type_sub = scene.fcd_vehicle_type
            
            # 4. Property Editing for Active Vehicle Part
            obj = context.active_object
            if obj and hasattr(obj, "fcd_pg_mech_props"):
                props = obj.fcd_pg_mech_props
                if props.is_part and props.category == 'VEHICLE':
                    box.separator()
                    edit_box = box.box()
                    edit_box.label(text=f"Editing {obj.name}", icon='PROPERTIES')
                    
                    # Safe type name extraction
                    raw_type = str(props.type_vehicle)
                    type_name = raw_type.replace('_', ' ').title()
                    edit_box.label(text=f"Preset: {type_name}", icon='OUTLINER_OB_MESH')
                    
                    edit_col = edit_box.column(align=True)
                    edit_col.prop(props, "vehicle_length", text="Length")
                    edit_col.prop(props, "vehicle_width", text="Width")
                    edit_col.prop(props, "vehicle_height", text="Height")
                    
                    edit_box.separator()
                    edit_col = edit_box.column(align=True)
                    edit_col.prop(props, "vehicle_wheel_radius", text="Wheel Radius")
                    edit_col.prop(props, "vehicle_wheel_width", text="Wheel Width")
                    edit_col.prop(props, "vehicle_wheelbase", text="Wheelbase")
                    edit_col.prop(props, "vehicle_track_width", text="Track Width")
                    
                    edit_box.separator()
                    edit_box.operator("fcd.bake_mesh", text="Bake to Static Vehicle", icon='CHECKBOX_HLT')

def register():
    pass

def unregister():
    pass
