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

class FCD_PT_Dimensions_And_Precision_Transforms:
    """
    Dimensions & Precision Transforms panel.
    Generates parametric mesh-based dimension displays. In Object Mode, measures between
    selected object bounding box centers. In Edit Mode, automatically attaches Parametric
    Anchor hooks at each selection group's center, then generates the dimension between
    those hooks — no vertex-parenting required.
    Provides accurate scaling/transform tools for drafting precision.
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
            "Dimensions & Precision Transforms", 
            "fcd_show_panel_dimensions", 
            "fcd_panel_enabled_dimensions"
        )
        
        if is_expanded:
            # --- Section: Parametric Anchors (Moved from Procedural Toolkit) ---
            anchor_box = box.box()
            anchor_box.label(text="Parametric Anchors", icon='HOOK')
            
            # AI Editor Note: Enabled for both Edit and Object modes to support per-vertex and per-object hooks.
            row_anchor = anchor_box.row(align=True)
            row_anchor.operator("fcd.add_parametric_anchor", text="Attach Hook", icon='SPHERE')
            row_anchor.operator("fcd.add_marker", text="Attach Marker", icon='EMPTY_AXIS')

            # Persistent Control for Anchor Transforms (regardless of initial selection)
            if context.scene.fcd_hook_placement_mode:
                anchor_box.operator("fcd.toggle_hook_placement", text="Stop Hook/Marker Transform Mode", icon='CHECKMARK')
            else:
                anchor_box.operator("fcd.toggle_hook_placement", text="Start Hook/Marker Transform Mode", icon='TRANSFORM_ORIGINS')
            
            row_ops = anchor_box.row(align=True)
            row_ops.operator("fcd.bake_anchor", text="Update Selected", icon='MODIFIER_ON')
            row_ops.operator("fcd.cleanup_anchor", text="Remove Selected", icon='TRASH')

            # Contextual info for meshes with existing hooks
            if context.active_object and context.active_object.type == 'MESH':
                has_hooks = any(m.type == 'HOOK' for m in context.active_object.modifiers)
                if has_hooks:
                    anchor_box.label(text="Mesh has active hooks", icon='INFO')

            # --- Smart Dimension Toolkit (Unified) ---
            dim_toolkit_box = box.box()
            dim_toolkit_box.label(text="Dimension Generator & Preferences", icon='DRIVER_DISTANCE')
            
            # Global Preferences (For new dimensions)
            pref_col = dim_toolkit_box.column(align=True)
            pref_col.label(text="Default Preferences (New Assemblies):", icon='PREFERENCES')
            row_pref = pref_col.row(align=True)
            row_pref.prop(scene, "fcd_dim_arrow_scale", text="Arrow")
            row_pref.prop(scene, "fcd_dim_text_scale", text="Txt Size")
            row_pref2 = pref_col.row(align=True)
            row_pref2.prop(scene, "fcd_dim_line_thickness", text="Thickness")
            row_pref2.prop(scene, "fcd_dim_auto_scale_on_spawn", text="Auto Size")
            pref_col.prop(scene, "fcd_dim_offset", text="Default Offset")
            pref_col.prop(scene, "fcd_dim_axis", text="Measurement Mode")
            
            dim_toolkit_box.separator()
            col = dim_toolkit_box.column(align=True)
            col.operator("fcd.add_dimension", text="Generate Dimension", icon='ADD')
            
            # --- Remove Selected Dimension ---
            active_obj = context.active_object
            from .. import core
            dim_host = core.get_dimension_host(active_obj)
            is_dim = dim_host is not None
            
            if is_dim:
                col.separator()
                col.operator("fcd.remove_dimension", text="Remove Selected Dimension", icon='TRASH')
            
            # --- Unified Display Properties ---
            col.separator()
            if is_dim:
                # prop_box.label(text="Display Properties", icon='PROPERTIES')
                dim_props = dim_host.fcd_pg_dim_props
                
                # 'Length' allows for precise input of dimensions.
                col.prop(dim_props, "length", text="Line Length")
                
                row2 = col.row(align=True)
                row2.prop(dim_props, "arrow_scale", text="Arrow")
                row2.prop(dim_props, "text_scale", text="Text Size")
                
                col.prop(dim_props, "line_thickness", text="Line Thickness")
                col.prop(dim_props, "offset", text="Offset from Target")
                col.operator("fcd.dimension_auto_scale", text="Auto Size Components", icon='AUTO')
                
                col.prop(dim_props, "is_flipped", text="Flip Target Roles")
                col.prop(dim_props, "use_extension_lines", text="Use Extension Lines")
                col.prop(dim_props, "text_color", text="Label Color")
                # Architecture and Engineering fonts feature
                col.prop(dim_props, "font_name", text="Standard Font")
                col.prop(dim_props, "flip_text", text="Flip Text")
                col.prop(dim_props, "text_rotation", text="Text Rotation")
                col.prop(dim_props, "unit_display", text="Units")
                
                # Planar Display Mode Toggle
                col.separator()
                col.label(text="Dimension Offset Alignment", icon='VIEW_ORTHO')
                
                # Layout the options in a grid-like fashion
                row_pos = col.row(align=True)
                row_pos.prop(dim_props, "align_x", toggle=True, text="+X")
                row_pos.prop(dim_props, "align_y", toggle=True, text="+Y")
                row_pos.prop(dim_props, "align_z", toggle=True, text="+Z")
                
                row_neg = col.row(align=True)
                row_neg.prop(dim_props, "align_nx", toggle=True, text="-X")
                row_neg.prop(dim_props, "align_ny", toggle=True, text="-Y")
                row_neg.prop(dim_props, "align_nz", toggle=True, text="-Z")
                
                col.separator()
                col.label(text="Text Alignment", icon='ALIGN_CENTER')
                row_text = col.row(align=True)
                row_text.prop(dim_props, "text_alignment", expand=True)
            else:
                col.label(text="Select a dimension arrow to adjust", icon='INFO')

            # --- Accurate Scale (New) ---
            scale_box = box.box()
            scale_box.label(text="Accurate Scaling", icon='CON_FOLLOWPATH')
            col_scale = scale_box.column(align=True)
            
            row_axes = col_scale.row(align=True)
            row_axes.prop(scene, "fcd_scale_axes", index=0, text="X", toggle=True)
            row_axes.prop(scene, "fcd_scale_axes", index=1, text="Y", toggle=True)
            row_axes.prop(scene, "fcd_scale_axes", index=2, text="Z", toggle=True)
            
            col_scale.prop(scene, "fcd_scale_value", text="Target Dimension")
            col_scale.operator("fcd.accurate_scale", text="Apply Accurate Scale", icon='CHECKMARK')

def register():
    pass

def unregister():
    pass
