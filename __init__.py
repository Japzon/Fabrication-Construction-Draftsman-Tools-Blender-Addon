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
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Layouts & Systems Toolkit",
    "description": "A comprehensive toolkit for native, non-destructive URDF creation and rigging for ROS/Gazebo.",
    "category": "Import-Export",
    "doc_url": "https://github.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon.git",
    "tracker_url": "https://github.com/Japzon/Layouts-Systems-Draftsman-Toolkit-Addon/issues",
}

import bpy
from . import config
from . import core
from . import properties
from . import operators
from . import panels

# Helper to register all classes in a module
def register_module_classes(module):
    if hasattr(module, "register"):
        module.register()

def unregister_module_classes(module):
    if hasattr(module, "unregister"):
        module.unregister()

def register():
    # Register Core (Handlers)
    core.register()
    
    # Register Operators FIRST to ensure callbacks have access to them
    operators.register()
    
    # Register Properties
    properties.register()
    
    # Register Panels
    panels.register()

def unregister():
    # Unregister Panels
    panels.unregister()
    
    # Unregister Operators
    operators.unregister()
    
    # Unregister Properties
    properties.unregister()
    
    # Unregister Core
    core.unregister()

if __name__ == "__main__":
    register()
