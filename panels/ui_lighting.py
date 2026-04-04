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

class LSD_PT_Lighting_And_Atmosphere:
    """
    Overhauled 'Lighting & Atmosphere' panel with procedural presets
    and light source utility for type switching.
    """

    @staticmethod
    def poll(context: bpy.types.Context) -> bool:
        return context.scene.lsd_panel_enabled_lighting

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        props = getattr(scene, "lsd_pg_lighting_props", None)
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Lighting & Atmosphere", 
            "lsd_show_panel_lighting", 
            "lsd_panel_enabled_lighting"
        )
        
        if is_expanded:
            # --- GLOBAL ENVIRONMENT ---
            if props:
                ebbox = box.box()
                ebbox.label(text="Atmospheric Presets", icon='WORLD')
                ebbox.prop(props, "light_preset", text="Preset")
            else:
                box.label(text="Error: Lighting Settings (props) not found.", icon='ERROR')

            box.separator()
            
            # --- LIGHT SOURCE UTILITY ---
            lbox = box.box()
            lbox.label(text="Light Source Utility", icon='LIGHT_SUN')
            
            obj = context.active_object
            if obj and obj.type == 'LIGHT' and hasattr(obj, 'data'):
                light = obj.data
                main_col = lbox.column(align=True)
                
                row = main_col.row(align=True)
                row.label(text=f"Editing: {obj.name}", icon='INFO')
                
                main_col.separator()
                
                # Switcher Row
                row = main_col.row(align=True)
                row.prop(light, "type", text="Switch Type")
                row.prop(light, "energy", text="Intensity")
                
                # Colors also maintain relevance
                main_col.prop(light, "color", text="Color")
                
                # Additional prompt context
                main_col.separator()
                main_col.label(text="Intensity maintained during switch", icon='CHECKMARK')
            else:
                lbox.label(text="Select a light source to enable switching.", icon='INFO')
                lbox.separator()
                lbox.label(text="Dropdown will reveal when object is active", icon='LIGHT_DATA')

def register():
    pass

def unregister():
    pass
