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

class LSD_PT_Camera_Cinematography:
    """
    Standardized drawing helper for the Camera Studio.
    Provides path-binding, look-at targeting, and sensor setup.
    """
    bl_label = "Camera Studio & Pathing"
    bl_idname = "VIEW3D_PT_lsd_camera"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return getattr(context.scene, "lsd_panel_enabled_camera", True)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Camera Studio panel.
        """
        scene = context.scene
        obj = context.active_object
        
        # 1. Standardized Header (Adds the Expand/Close buttons to match other panels)
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Camera Studio & Pathing", 
            "lsd_show_panel_camera", 
            "lsd_panel_enabled_camera"
        )
        
        if is_expanded:
            if not obj or obj.type != 'CAMERA':
                # --- Quick Spawn Section ---
                b_spawn = box.box()
                b_spawn.label(text="Assign or Spawn Camera", icon='CAMERA_DATA')
                col = b_spawn.column(align=True)
                col.prop(scene, "lsd_camera_preset", text="Preset")
                col.separator()
                col.operator("lsd.create_camera", text="Spawn New Camera", icon='ADD')
                
                box.label(text="Or select an existing Camera to begin.", icon='INFO')
                return

            props = obj.lsd_pg_mech_props
            
            # --- Lens & Sensor Setup ---
            box.separator()
            box.label(text="Lens & Sensor Setup", icon='CAMERA_DATA')
            col = box.column(align=True)
            col.prop(props, "camera_focal_length", text="Focal Length (mm)")
            col.separator()
            col.prop(props, "camera_dof_enabled", text="Use Depth of Field", toggle=True)
            if props.camera_dof_enabled:
                col.prop(props, "camera_fstop", text="F-Stop")
            
            # --- Path & Kinematics ---
            box.separator()
            box.label(text="Path & Kinematics", icon='ANIM')
            col = box.column(align=True)
            col.prop(props, "camera_path", text="Animation Path")
            if props.camera_path:
                 col.prop(props, "camera_path_offset", text="Path Position", slider=True)
            
            col.separator()
            col.prop(props, "camera_target", text="Look-At Target")
            
            # --- Execution ---
            box.separator()
            row = box.row(align=True)
            row.scale_y = 1.4
            row.operator("lsd.camera_setup", text="Apply Setup", icon='CHECKMARK')
            row.operator("lsd.camera_look_through", text="View", icon='HIDE_OFF')

def register():
    pass

def unregister():
    pass
