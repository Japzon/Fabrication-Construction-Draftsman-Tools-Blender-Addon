# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T (GPL COMPLIANT)
# This add-on is protected under the GNU General Public License (GPL) to ensure 
# fair use and free distribution. The original architecture, source code, and 
# design logic are the intellectual property of Greenlex Systems Services Incorporated. 
#
# No party is authorized to claim authorship or ownership of this original work.
# --------------------------------------------------------------------------------



import bpy
from . import ui_common

class URDF_PT_AssetLibrarySystem:
    """
    Asset Library System Panel Drawing Logic.
    Provides a clean workflow for managing Blender asset libraries and catalogs.
    """
    @classmethod
    def poll(cls, context):
        if not context or not hasattr(context, "scene"): return False
        return getattr(context.scene, "urdf_panel_enabled_assets", False)

    @staticmethod
    def draw(layout, context):
        scene = context.scene
        asset_props = scene.urdf_asset_props
        box = layout.box()

        # Header with auto-collapse support
        is_expanded = getattr(scene, "urdf_show_panel_assets", False)
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)

        op = row.operator("urdf.toggle_panel_visibility", text="Asset Library System", emboss=False, icon=icon)
        if op:
            op.panel_property = "urdf_show_panel_assets"

        if hasattr(scene, "urdf_panel_enabled_assets"):
            close_op = row.operator("urdf.disable_panel", text="", icon='X')
            if close_op: close_op.prop_name = "urdf_panel_enabled_assets"

        if is_expanded:
            col = box.column(align=False)
            col.separator()

            # --- Select Target Library ---
            b1 = col.box()
            b1.label(text="Select Target Library", icon='FILE_FOLDER')
            b1.prop(asset_props, "target_library", text="Library")
            row_lib = b1.row(align=True)
            row_lib.prop(asset_props, "add_library_path", text="")
            row_lib.operator("urdf.add_asset_library", text="Add Library", icon='ADD')

            # --- Register Catalog ---
            b2 = col.box()
            b2.label(text="Register Catalog", icon='FILE_NEW')
            b2.prop(asset_props, "new_catalog_name", text="Name")
            b2.operator("urdf.register_asset_catalog", text="Register Catalog", icon='ADD')

            # --- Select Catalog ---
            b3 = col.box()
            b3.label(text="Select Catalog", icon='ASSET_MANAGER')
            b3.prop(asset_props, "selected_catalog", text="Catalog")

            # --- Import Selected to Catalog ---
            b4 = col.box()
            b4.label(text="Mark & Upload Selection", icon='EXPORT')
            b4.operator("urdf.mark_and_upload_asset", text="Import Selected to Catalog", icon='EXPORT')

            # --- Open Asset Browser ---
            b5 = col.box()
            b5.label(text="Open Asset Browser", icon='WINDOW')
            b5.operator("urdf.open_asset_browser", text="Open Asset Browser", icon='WINDOW')

            # --- Import External 3D File ---
            b6 = col.box()
            b6.label(text="Import External 3D File", icon='IMPORT')
            b6.prop(asset_props, "import_source_filepath", text="Import Target")
            b6.prop(asset_props, "import_target_library", text="Library")
            b6.prop(asset_props, "import_target_catalog", text="Catalog")
            b6.operator("urdf.import_to_asset_catalog", text="Import & Register as Asset", icon='APPEND_BLEND')

def register():
    # Registration is handled by the main panel loop or __init__.py
    pass

def unregister():
    pass

