# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import bpy
from . import ui_common

class URDF_PT_DimensionsAndMeasuring:
    """
    Dimensions & Measuring panel.
    Generates parametric mesh-based dimension displays from selected object bounding boxes,
    with adjustable visual properties and precise measurement labels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return getattr(context.scene, "urdf_panel_enabled_dimensions", False)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()

        is_expanded = getattr(scene, "urdf_show_panel_dimensions", False)
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Dimensions & Measuring", emboss=False, icon=icon)
        if op:
            op.panel_property = "urdf_show_panel_dimensions"
        row.prop(scene, "urdf_show_panel_dimensions", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        if close_op:
            close_op.prop_name = "urdf_panel_enabled_dimensions"

        if not is_expanded:
            return

        # --- Smart Dimension Generator ---
        gen_box = box.box()
        col = gen_box.column(align=True)
        col.operator("urdf.add_dimension", text="Generate Dimensions for Selected", icon='DRIVER_DISTANCE')
        
        # --- Remove Selected Dimension ---
        active_obj = context.active_object
        is_dim = active_obj and active_obj.get("urdf_is_dimension")
        
        if is_dim:
            col.separator()
            col.operator("urdf.remove_dimension", text="Remove Selected Dimension", icon='TRASH')

        # --- Display Properties ---
        prop_box = box.box()
        # The display properties should only fully appear when an arrow is selected
        if is_dim:
            prop_box.label(text="Display Properties", icon='PROPERTIES')
            col2 = prop_box.column(align=True)
            
            # AI Editor Note: 'Length' allows for precise input of dimensions.
            col2.prop(active_obj, "urdf_dim_length", text="Length")
            
            row2 = col2.row(align=True)
            row2.prop(active_obj, "urdf_dim_arrow_scale", text="Arrow")
            row2.prop(active_obj, "urdf_dim_text_scale", text="Label")
            col2.prop(active_obj, "urdf_dim_line_thickness", text="Line Thickness")
            col2.prop(active_obj, "urdf_dim_offset", text="Offset from Object")
            col2.prop(active_obj, "urdf_dim_extension", text="End Extension")
            col2.prop(active_obj, "urdf_dim_text_color", text="Label Color")
            col2.prop(active_obj, "urdf_dim_unit_display", text="Units")
        else:
            # A display to select a dimension arrow is shown when no arrows are selected
            row = prop_box.row(align=True)
            row.alignment = 'CENTER'
            row.label(text="Select a dimension arrow to adjust", icon='INFO')

def register():
    pass

def unregister():
    pass

