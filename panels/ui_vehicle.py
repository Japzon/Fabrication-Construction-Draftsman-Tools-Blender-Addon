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

class URDF_PT_VehiclePresets:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Vehicle Presets' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """
    
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return context.scene.urdf_panel_enabled_vehicle

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        # --- Header ---
        box, is_expanded = ui_common.draw_panel_header(layout, context, "Vehicle Presets", "urdf_show_panel_vehicle", "urdf_panel_enabled_vehicle")

        if is_expanded:
            # --- Generation Size Constraint ---
            cage_box = box.box()
            cage_box.label(text="Base Scale (Length)", icon='SHADING_BBOX')
            cage_box.prop(scene, "urdf_use_generation_cage")
            row = cage_box.row()
            row.enabled = scene.urdf_use_generation_cage
            row.prop(scene, "urdf_generation_cage_size")

            # Selection
            sel_box = box.box()
            sel_box.prop(scene, "urdf_vehicle_type", text="Vehicle Model")
            
            gen_row = box.row()
            op = gen_row.operator("urdf.create_part", text="Spawn Vehicle", icon='AUTOMOBILE')
            op.category = 'VEHICLE'
            op.type_sub = scene.urdf_vehicle_type
            # Note: create_part uses urdf_part_type by default, but we can override or use scene prop
            # For simplicity, we'll ensure create_part logic handles VEHICLE correctly.
            
            # --- Active Object Editor ---
            obj = context.active_object
            if obj and hasattr(obj, "urdf_mech_props") and obj.urdf_mech_props.category == 'VEHICLE':
                box.separator()
                edit_box = box.box()
                props = obj.urdf_mech_props
                
                edit_box.label(text=f"Editing {props.type_vehicle.title()}", icon='OUTLINER_OB_MESH')
                
                col = edit_box.column(align=True)
                col.prop(props, "vehicle_length")
                col.prop(props, "vehicle_width")
                col.prop(props, "vehicle_height")
                
                edit_box.separator()
                col = edit_box.column(align=True)
                col.prop(props, "vehicle_wheel_radius")
                col.prop(props, "vehicle_wheel_width")
                col.prop(props, "vehicle_wheelbase")
                col.prop(props, "vehicle_track_width")
                
                # Bake Button
                edit_box.separator()
                row = edit_box.row()
                row.operator("urdf.bake_mesh", text="Bake Vehicle Mesh", icon='CHECKMARK')

def register():
    pass

def unregister():
    pass
