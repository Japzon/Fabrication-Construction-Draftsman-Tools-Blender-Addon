# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
# --------------------------------------------------------------------------------

import bpy
from . import ui_common
from .ui_parts import LSD_PT_Mechanical_Presets
from .ui_electronics import LSD_PT_Electronic_Presets
from .ui_architectural import LSD_PT_Architectural_Presets
from .ui_vehicle import LSD_PT_Vehicle_Presets

class LSD_PT_Presets:
    """
    Consolidated Presets panel acting as a single container for:
    - Mechanical
    - Electronic
    - Architectural
    - Vehicle
    """
    
    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "lsd_panel_enabled_presets", True)

    @staticmethod
    def draw(layout, context):
        # Master Panel Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Presets", 
            "lsd_show_panel_presets", 
            "lsd_panel_enabled_presets"
        )
        
        if is_expanded:
            # Using an aligned column to pull the boxes closer together.
            col = box.column(align=True)
            
            # 1. Mechanical
            if context.scene.lsd_panel_enabled_parts:
                mech_box = col.box()
                header = mech_box.row()
                header.prop(context.scene, "lsd_show_panel_parts", 
                            icon='DISCLOSURE_TRI_DOWN' if context.scene.lsd_show_panel_parts else 'DISCLOSURE_TRI_RIGHT', 
                            text="", emboss=False)
                header.label(text="Mechanical", icon='MODIFIER')
                if context.scene.lsd_show_panel_parts:
                    from .ui_parts import lsd_draw_mechanical_presets_content
                    lsd_draw_mechanical_presets_content(mech_box, context)

            # 2. Electronic
            if context.scene.lsd_panel_enabled_electronics:
                elec_box = col.box()
                header = elec_box.row()
                header.prop(context.scene, "lsd_show_panel_electronics", 
                            icon='DISCLOSURE_TRI_DOWN' if context.scene.lsd_show_panel_electronics else 'DISCLOSURE_TRI_RIGHT', 
                            text="", emboss=False)
                header.label(text="Electronics", icon='OUTLINER_OB_FORCE_FIELD')
                if context.scene.lsd_show_panel_electronics:
                    from .ui_electronics import lsd_draw_electronic_presets_content
                    lsd_draw_electronic_presets_content(elec_box, context)

            # 3. Architectural
            if context.scene.lsd_panel_enabled_architectural:
                arch_box = col.box()
                header = arch_box.row()
                header.prop(context.scene, "lsd_show_panel_architectural", 
                            icon='DISCLOSURE_TRI_DOWN' if context.scene.lsd_show_panel_architectural else 'DISCLOSURE_TRI_RIGHT', 
                            text="", emboss=False)
                header.label(text="Architectural", icon='MOD_BUILD')
                if context.scene.lsd_show_panel_architectural:
                    from .ui_architectural import lsd_draw_architectural_presets_content
                    lsd_draw_architectural_presets_content(arch_box, context)

            # 4. Vehicle
            if context.scene.lsd_panel_enabled_vehicle:
                veh_box = col.box()
                header = veh_box.row()
                header.prop(context.scene, "lsd_show_panel_vehicle", 
                            icon='DISCLOSURE_TRI_DOWN' if context.scene.lsd_show_panel_vehicle else 'DISCLOSURE_TRI_RIGHT', 
                            text="", emboss=False)
                header.label(text="Vehicle", icon='OUTLINER_OB_SPEAKER')
                if context.scene.lsd_show_panel_vehicle:
                    from .ui_vehicle import lsd_draw_vehicle_presets_content
                    lsd_draw_vehicle_presets_content(veh_box, context)
