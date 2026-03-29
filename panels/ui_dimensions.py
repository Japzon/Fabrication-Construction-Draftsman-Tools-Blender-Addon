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

class FCD_PT_Dimensions_And_Measuring:
    """
    Dimensions & Measuring panel.
    Generates parametric mesh-based dimension displays from selected object bounding boxes,
    with adjustable visual properties and precise measurement labels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return getattr(context.scene, "fcd_panel_enabled_dimensions", False)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Dimensions toolkit.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Dimensions & Measuring", 
            "fcd_show_panel_dimensions", 
            "fcd_panel_enabled_dimensions"
        )
        
        if is_expanded:
            # --- Smart Dimension Generator ---
            gen_box = box.box()
            col = gen_box.column(align=True)
            col.operator("fcd.add_dimension", text="Generate Dimensions for Selected", icon='DRIVER_DISTANCE')
            
            # --- Remove Selected Dimension ---
            active_obj = context.active_object
            
            # AI Editor Note: Robustly find the dimension host (the label object)
            # from any part of the dimension assembly.
            from .. import core
            dim_host = core.get_dimension_host(active_obj)
            is_dim = dim_host is not None
            
            if is_dim:
                col.separator()
                # Create a custom operator or use fcd.remove_dimension with host
                op = col.operator("fcd.remove_dimension", text="Remove Selected Dimension", icon='TRASH')
                # Note: fcd.remove_dimension should probably handle the host selection
            
            # --- Display Properties ---
            prop_box = box.box()
            if is_dim:
                prop_box.label(text="Display Properties", icon='PROPERTIES')
                col2 = prop_box.column(align=True)
                dim_props = dim_host.fcd_pg_dim_props
                
                # 'Length' allows for precise input of dimensions.
                col2.prop(dim_props, "length", text="Line Length")
                
                row2 = col2.row(align=True)
                row2.prop(dim_props, "arrow_scale", text="Arrow")
                row2.prop(dim_props, "text_scale", text="Text Size")
                col2.prop(dim_props, "line_thickness", text="Line Thickness")
                col2.prop(dim_props, "offset", text="Offset from Target")
                col2.prop(dim_props, "extension_line", text="Extension Line")
                col2.prop(dim_props, "text_color", text="Label Color")
                col2.prop(dim_props, "flip_text", text="Flip Text")
                col2.prop(dim_props, "unit_display", text="Units")
                
                # Planar Display Mode Toggle
                col2.separator()
                col2.label(text="Dimension Alignment", icon='VIEW_ORTHO')
                row3 = col2.row(align=True)
                
                # Layout the options in a grid-like fashion
                row_pos = col2.row(align=True)
                row_pos.prop(dim_props, "align_x", toggle=True, text="+X")
                row_pos.prop(dim_props, "align_y", toggle=True, text="+Y")
                row_pos.prop(dim_props, "align_z", toggle=True, text="+Z")
                
                row_neg = col2.row(align=True)
                row_neg.prop(dim_props, "align_nx", toggle=True, text="-X")
                row_neg.prop(dim_props, "align_ny", toggle=True, text="-Y")
                row_neg.prop(dim_props, "align_nz", toggle=True, text="-Z")
                
                col2.separator()
                col2.label(text="Text Alignment", icon='ALIGN_CENTER')
                row_text = col2.row(align=True)
                row_text.prop(dim_props, "text_alignment", expand=True)
            else:
                row = prop_box.row(align=True)
                row.alignment = 'CENTER'
                row.label(text="Select a dimension arrow to adjust", icon='INFO')

def register():
    pass

def unregister():
    pass
