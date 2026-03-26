bl_info = {
    "name": "Fabrication & Construction Draftsman Tools (Automated)",
    "author": "Gemini",
    "version": (7, 45, 0),
    "blender": (4, 5, 6),
    "location": "View3D > Sidebar > Draftsman Tools",
    "description": "A comprehensive toolkit for native, non-destructive URDF creation and rigging for ROS/Gazebo.",
    "category": "Import-Export",
    "doc_url": "https://github.com/Japzon/Fabrication-Construction-Draftsman-Tools-Automated.git",
    "tracker_url": "https://github.com/Japzon/Fabrication-Construction-Draftsman-Tools-Automated/issues",
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
    
    # Register Properties
    properties.register()
    
    # Register Operators
    operators.register()
    
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
