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

class LSD_PT_Dimensions_And_Precision_Transforms:

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

        return getattr(context.scene, "lsd_panel_enabled_dimensions", False)

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
            "lsd_show_panel_dimensions", 
            "lsd_panel_enabled_dimensions"
        )

        

        if is_expanded:

            # --- Section: Parametric Anchors (Moved from Procedural Toolkit) ---

            anchor_box = box.box()

            anchor_box.label(text="Parametric Anchors", icon='HOOK')

            

            # AI Editor Note: Enabled for both Edit and Object modes to support per-vertex and per-object hooks.

            row_anchor = anchor_box.row(align=True)

                        # AI Editor Note: Added anchor sizing controls (Project Task 1.1.2)
            row_size = anchor_box.row(align=True)
            row_size.prop(scene, "lsd_anchor_initial_size", text="Initial Size")
            row_size.prop(scene, "lsd_anchor_auto_size", text="Auto-Size", icon='AUTO')
            anchor_box.prop(scene, "lsd_anchor_placement_source", text="Generate At")
            anchor_box.prop(scene, "lsd_anchor_grouping_mode", text="Anchor Grouping")
            
            anchor_box.separator()

            # AI Editor Note: Enabled for both Edit and Object modes to support per-vertex and per-object hooks.
            row_anchor = anchor_box.row(align=True)
            row_anchor.operator("lsd.add_parametric_anchor", text="Attach Hook", icon='ORIENTATION_GLOBAL')

            row_anchor.operator("lsd.add_marker", text="Attach Marker", icon='EMPTY_AXIS')

            # Persistent Control for Anchor Transforms (regardless of initial selection)

            if context.scene.lsd_hook_placement_mode:

                anchor_box.operator("lsd.toggle_hook_placement", text="Stop Anchor Transform Mode", icon='CHECKMARK')

            else:

                anchor_box.operator("lsd.toggle_hook_placement", text="Start Anchor Transform Mode", icon='TRANSFORM_ORIGINS')

            

            row_ops = anchor_box.row(align=True)

            row_ops.operator("lsd.bake_anchor", text="Update Selected", icon='MODIFIER_ON')

            row_ops.operator("lsd.cleanup_anchor", text="Remove Selected", icon='TRASH')

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

            # Row 0: Header + Auto Size Toggle
            row_header = pref_col.row(align=True)
            row_header.label(text="Default Preferences (New Assemblies):", icon='PREFERENCES')
            row_header.operator("lsd.dimension_auto_calculate_global", text="Auto Calculate", icon='AUTO')

            # Row 1: Arrow + Txt Size
            row_size = pref_col.row(align=True)
            row_size.prop(scene, "lsd_dim_arrow_scale", text="Arrow")
            row_size.prop(scene, "lsd_dim_text_scale", text="Txt Size")

            # Row 2: Thickness + Txt Off
            row_thick = pref_col.row(align=True)
            row_thick.prop(scene, "lsd_dim_line_thickness", text="Thickness")
            row_thick.prop(scene, "lsd_dim_text_offset", text="Txt Off")

            # Row 3: Default Offset
            pref_col.prop(scene, "lsd_dim_offset", text="Default Offset")

            

            dim_toolkit_box.separator()

            col = dim_toolkit_box.column(align=True)

            col.operator("lsd.add_dimension", text="Generate Dimension", icon='ADD')

            

            # --- Remove Selected Dimension ---

            active_obj = context.active_object

            from .. import core

            dim_host = core.get_dimension_host(active_obj)

            is_dim = dim_host is not None

            

            if is_dim:

                col.separator()

                col.operator("lsd.remove_dimension", text="Remove Selected Dimensions", icon='TRASH')

            

            # --- Unified Display Properties ---

            col.separator()

            if is_dim:

                # prop_box.label(text="Display Properties", icon='PROPERTIES')

                dim_props = dim_host.lsd_pg_dim_props

                

                # 'Length' allows for precise input of dimensions.

                col.prop(dim_props, "length", text="Line Length")

                

                row2 = col.row(align=True)

                row2.prop(dim_props, "arrow_scale", text="Arrow")
                row2.prop(dim_props, "text_scale", text="Text Size")
                col.prop(dim_props, "text_offset", text="Text Offset")

                

                col.prop(dim_props, "line_thickness", text="Line Thickness")

                col.prop(dim_props, "offset", text="Offset from Target")

                col.operator("lsd.dimension_auto_scale", text="Auto Size Components", icon='AUTO')
                col.operator("lsd.register_default_proportions", text="Register Custom Proportions", icon='SETTINGS')

                

                col.prop(dim_props, "is_flipped", text="Flip Target Roles")

                col.prop(dim_props, "use_extension_lines", text="Use Extension Lines")

                color_box = col.box()
                scene = context.scene # Defined locally for the property check
                color_row = color_box.row(align=True)
                color_row.prop(scene, "lsd_dim_global_text_color_sync", text="Force Global Sync", icon='WORLD')
                
                if scene.lsd_dim_global_text_color_sync:
                    color_box.prop(scene, "lsd_dim_universal_text_color", text="Universal Label Color")
                else:
                    color_box.prop(dim_props, "text_color", text="Selected Label Color")

                # Architecture and Engineering fonts feature

                row_style = col.row(align=True)
                row_style.label(text="Font Style:")
                col.prop(dim_props, "font_name", text="")
                row_style_inner = col.row(align=True)
                row_style_inner.prop(dim_props, "font_bold", toggle=True, icon='BOLD')
                row_style_inner.prop(dim_props, "font_italic", toggle=True, icon='ITALIC')
                col.prop(dim_props, "flip_text", text="Flip Text")

                col.prop(dim_props, "unit_display", text="Units")

                # --- Swapped Section: Alignment Tools ---
                col.separator()
                
                # 1. Text Alignment (Refined Priority)
                col.label(text="Text Alignment", icon='ALIGN_CENTER')
                row_text = col.row(align=True)
                row_text.prop(dim_props, "text_alignment", expand=True)

                col.separator()

                # 2. Offset Alignment (Orthographic Constraints)
                col.label(text="Dimension Offset Alignment", icon='VIEW_ORTHO')
                
                grid_col = col.column(align=True)
                row_pos = grid_col.row(align=True)
                row_pos.prop(dim_props, "align_x", toggle=True, text="+X")
                row_pos.prop(dim_props, "align_y", toggle=True, text="+Y")
                row_pos.prop(dim_props, "align_z", toggle=True, text="+Z")
                
                row_neg = grid_col.row(align=True)
                row_neg.prop(dim_props, "align_nx", toggle=True, text="-X")
                row_neg.prop(dim_props, "align_ny", toggle=True, text="-Y")
                row_neg.prop(dim_props, "align_nz", toggle=True, text="-Z")


                

            # --- Dimensions Master Interface (Consolidated Manager) ---
            # Provides a unified list of dimensions for selective renaming, length management, and baking.
            col.separator()
            master_box = col.box()
            master_box.label(text="Dimensions Master Interface", icon='OUTLINER')
            
            # New Feature: Manual List Management
            row = master_box.row()
            row.operator("lsd.add_to_dimension_master", text="Track Selected Dimension", icon='ADD')
            
            master = context.scene.lsd_dimensions_master
            if not master:
                master_box.label(text="No tracked dimensions in master list.", icon='INFO')
            else:
                for idx, item in enumerate(master):
                    host = item.obj
                    if not host:
                        continue
                    
                    row = master_box.row(align=True)
                    # Selection (Tooltip derived from bl_label)
                    op = row.operator("lsd.select_object_by_name", text="", icon='RESTRICT_SELECT_OFF')
                    op.target_name = host.name
                    
                    # Name & Length sync
                    row.prop(host, "name", text="")
                    row.prop(host.lsd_pg_dim_props, "length", text="Length")
                    
                    # LINK DRIVER (Eyedropper) - Category 4 Logic
                    row.prop(item, "driver_target", text="", icon='EYEDROPPER')

                    # New Feature: Individual removal (X)
                    rem_op = row.operator("lsd.remove_from_dimension_master", text="", icon='X')
                    rem_op.index = idx
            
            # New Feature: Consolidated Exposure (Protocol Switch)
            if master:
                master_box.separator()
                # AI Editor Note: 'Bake' now triggers tool property consolidation
                master_box.operator("lsd.bake_dimensions_master", text="Group for Master Control", icon='GEOMETRY_NODES')


            # --- Accurate Scale (New) ---

            scale_box = box.box()

            scale_box.label(text="Accurate Scaling", icon='CON_FOLLOWPATH')

            col_scale = scale_box.column(align=True)
            col_scale.prop(scene, "lsd_scale_mode", text="Scaling Mode")
            col_scale.prop(scene, "lsd_scale_pivot", text="Pivot Point")

            col_scale.separator()

            row_axes = col_scale.row(align=True)
            row_axes.prop(scene, "lsd_scale_axes", index=0, text="X", toggle=True)
            row_axes.prop(scene, "lsd_scale_axes", index=1, text="Y", toggle=True)
            row_axes.prop(scene, "lsd_scale_axes", index=2, text="Z", toggle=True)

            col_scale.prop(scene, "lsd_scale_value", text="Target Dimension")

            col_scale.separator()

            # Live Execution Controls (rearranged)
            col_scale.prop(scene, "lsd_scale_realtime", text="Live Calibration", icon='TIME')
            if not scene.lsd_scale_realtime:
                 col_scale.operator("lsd.accurate_scale", text="Commit Scale", icon='CHECKMARK')

            


class LSD_PT_Dimensions_Tool_Properties(bpy.types.Panel):
    """
    Exposes the persistent Dimensions Master Interface.
    Visible in Properties Editor -> Tool tab OR 3D Viewport Sidebar -> Tool tab.
    """
    bl_label = "Dimensions Grouped Control"
    bl_idname = "LSD_PT_Dimensions_Tool_Properties"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # Show if we have grouped dimensions or a dimension is selected
        grouped = getattr(context.scene, "lsd_dimensions_grouped", [])
        if len(grouped) > 0:
            return True
            
        obj = context.active_object
        if obj:
             from .. import core
             if core.get_dimension_host(obj):
                  return True
        return False

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene
        grouped_sets = scene.lsd_dimensions_grouped_sets
        
        if not grouped_sets:
            layout.label(text="No grouped dimensions.", icon='INFO')
            return

        for g_idx, group in enumerate(grouped_sets):
            box = layout.box()
            header = box.row()
            # Collapse/Expand Toggle
            icon = 'DISCLOSURE_TRI_DOWN' if group.is_expanded else 'DISCLOSURE_TRI_RIGHT'
            header.prop(group, "is_expanded", text="", icon=icon, emboss=False)
            
            # Group Naming & Management Actions
            header.prop(group, "name", text="")
            
            manage_row = header.row(align=True)
            imp_op = manage_row.operator("lsd.import_grouped_dimensions_back", text="", icon='IMPORT')
            imp_op.group_index = g_idx
            
            del_op = manage_row.operator("lsd.clear_grouped_dimensions", text="", icon='TRASH')
            del_op.group_index = g_idx

            if group.is_expanded:
                box.separator()
                for idx, item in enumerate(group.items):
                    host = item.obj
                    if not host: continue
                    
                    row = box.row(align=True)
                    # Sync Mode Toggle (Manual vs Link)
                    icon = 'DOT' if host.lsd_pg_dim_props.is_manual else 'OUTLINER_OB_FORCE_FIELD'
                    row.prop(host.lsd_pg_dim_props, "is_manual", text="", icon=icon, emboss=False)
                    
                    # Selection & Focus
                    op = row.operator("lsd.select_object_by_name", text="", icon='RESTRICT_SELECT_OFF')
                    op.target_name = host.name
                    
                    # Sub-Row for property controls
                    controls = row.row(align=True)
                    controls.prop(host, "name", text="")
                    controls.prop(host.lsd_pg_dim_props, "length", text="Length")
                    
                    # Removal (Individual)
                    rem_op = row.operator("lsd.remove_from_dimension_master", text="", icon='X')
                    rem_op.index = idx
                    rem_op.group_index = g_idx
                    rem_op.is_grouped = True

def register():
    bpy.utils.register_class(LSD_PT_Dimensions_Tool_Properties)

def unregister():
    bpy.utils.unregister_class(LSD_PT_Dimensions_Tool_Properties)

