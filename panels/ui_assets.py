import bpy
from . import ui_common

class URDF_PT_AssetLibrarySystem:
    """
    Overhauled Asset Library System Panel Drawing Logic.
    Implements a one-click, step-by-step workflow for asset management.
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
        
        # 0. Header with auto-collapse support
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
            
            # --- STEP 1: Register Category ---
            b1 = col.box()
            b1.label(text="Step 1: Register Category", icon='FILE_NEW')
            b1.prop(asset_props, "category_name", text="Name")
            b1.operator("urdf.register_asset_category", text="One-Click Register", icon='ADD')
            
            # --- STEP 2: Mark & Upload ---
            b2 = col.box()
            b2.label(text="Step 2: Mark & Upload Selection", icon='ASSET_MANAGER')
            b2.prop(asset_props, "target_library", text="To Library")
            b2.operator("urdf.mark_and_upload_asset", text="Mark Selected as Asset", icon='EXPORT')
            
            # --- STEP 3: Open Asset Library ---
            b3 = col.box()
            b3.label(text="Step 3: Open Asset Library", icon='WINDOW')
            b3.operator("urdf.open_asset_browser", text="Open Browser Window", icon='WINDOW')
            
            # --- STEP 4: Import External ---
            b4 = col.box()
            b4.label(text="Step 4: Import External 3D File", icon='IMPORT')
            # Note: The operator itself handles the file selection via ImportHelper
            b4.operator("urdf.import_to_asset_category", text="Import & Mark as Asset", icon='APPEND_BLEND')

def register():
    # Registration is handled by the main panel loop or __init__.py
    pass

def unregister():
    pass
