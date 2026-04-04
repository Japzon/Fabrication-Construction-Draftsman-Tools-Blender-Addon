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

class LSD_PT_Asset_Library_System:
    """
    Asset Library System Panel Drawing Logic.
    Provides a clean workflow for managing Blender asset libraries and catalogs.
    """
    @classmethod
    def poll(cls, context):
        if not context or not hasattr(context, "scene"): return False
        return getattr(context.scene, "lsd_panel_enabled_assets", False)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        asset_props = scene.lsd_pg_asset_props
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Asset Library System", 
            "lsd_show_panel_assets", 
            "lsd_panel_enabled_assets"
        )
        
        if is_expanded:
            col = box.column(align=False)
            col.separator()

            # --- Select Target Library ---
            b1 = col.box()
            b1.label(text="Select Target Library", icon='FILE_FOLDER')
            row_target = b1.row(align=True)
            row_target.prop(asset_props, "target_library", text="Library")
            op = row_target.operator("lsd.browse_library", icon='FILE_FOLDER', text="")
            op.prop_name = "target_library"
            row_lib = b1.row(align=True)
            row_lib.prop(asset_props, "add_library_path", text="")
            op = row_lib.operator("lsd.browse_library", icon='FILE_FOLDER', text="")
            op.prop_name = "add_library_path"
            row_lib.operator("lsd.add_asset_library", text="Add Library", icon='ADD')

            # --- Register Catalog ---
            b2 = col.box()
            b2.label(text="Register Catalog", icon='FILE_NEW')
            b2.prop(asset_props, "new_catalog_name", text="Name")
            b2.operator("lsd.register_asset_catalog", text="Register Catalog", icon='ADD')

            # --- Select Catalog ---
            b3 = col.box()
            b3.label(text="Select Catalog", icon='ASSET_MANAGER')
            b3.prop(asset_props, "selected_catalog", text="Catalog")

            # --- Import Selected to Catalog ---
            b4 = col.box()
            b4.label(text="Mark & Upload Selection", icon='EXPORT')
            b4.operator("lsd.mark_and_upload_asset", text="Import Selected to Catalog", icon='EXPORT')

            # --- Open Asset Browser ---
            b5 = col.box()
            b5.label(text="Open Asset Browser", icon='WINDOW')
            b5.operator("lsd.open_asset_browser", text="Open Asset Browser", icon='WINDOW')

            # --- Import External 3D File ---
            b6 = col.box()
            b6.label(text="Import External 3D File", icon='IMPORT')
            b6.prop(asset_props, "import_source_filepath", text="Import Target")
            row_imp = b6.row(align=True)
            row_imp.prop(asset_props, "import_target_library", text="Library")
            op = row_imp.operator("lsd.browse_library", icon='FILE_FOLDER', text="")
            op.prop_name = "import_target_library"
            b6.prop(asset_props, "import_target_catalog", text="Catalog")
            b6.operator("lsd.import_to_asset_catalog", text="Import & Register as Asset", icon='APPEND_BLEND')

def register():
    # Registration is handled by the main panel loop or __init__.py
    pass

def unregister():
    pass

