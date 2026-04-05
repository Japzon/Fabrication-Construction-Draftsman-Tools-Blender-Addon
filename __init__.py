# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# Licensed under the GNU General Public License (GPL).
# Original Architecture & Logic by Greenlex Systems Services Incorporated.
#
# No person or organization is authorized to misrepresent this work or claim 
# original authorship for themselves. Proper attribution is mandatory.
# --------------------------------------------------------------------------------

bl_info = {
    "name": "Layouts & Systems Draftsman Toolkit",
    "author": "Greenlex Systems Services Incorporated",
    "version": (1, 3, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Layouts & Systems Toolkit",
    "description": "A comprehensive toolkit for native, non-destructive URDF creation and rigging for ROS/Gazebo.",
    "category": "Import-Export",
    "doc_url": "https://github.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon.git",
    "tracker_url": "https://github.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon/issues",
}

# Project Task: Robust Registration System (Project Task 1.1.2)
# Handles module reloading to prevent 'ghost' notifications in Preferences.
if "bpy" in locals():
    import importlib
    if "core" in locals(): importlib.reload(core)
    if "properties" in locals(): importlib.reload(properties)
    if "operators" in locals(): importlib.reload(operators)
    if "panels" in locals(): importlib.reload(panels)
    if "config" in locals(): importlib.reload(config)

import bpy
from . import config
from . import core
from . import properties
from . import operators
from . import panels

def register():
    # 0. Hard Registry Cleanup - Clears the persistent 'Missing Add-ons' warning
    try:
        legacy_ids = ["fabrication_construction_draftsman_tools", "fabrication_construction_draftman_tools", "Fabrication_Construction_Draftsman_Tools_Blender_Addon"]
        addon_prefs = bpy.context.preferences.addons
        for old_id in legacy_ids:
            if old_id in addon_prefs: # Standard ID check
                 try: addon_prefs.remove(addon_prefs[old_id])
                 except: pass # Fallback
                 print(f"[LSD] Registry Purge: Cleared ghost '{old_id}'.")
    except:
        pass

    # 1. Properties - Scene attributes must exist before operators/panels call them
    properties.register()
    
    # 2. Operators - Register commands
    operators.register()
    
    # 3. Core - Handlers and logic
    core.register()
    
    # 4. Panels - UI
    panels.register()

def unregister():
    # Unregister in reverse order
    panels.unregister()
    core.unregister()
    operators.unregister()
    properties.unregister()

if __name__ == "__main__":
    register()
