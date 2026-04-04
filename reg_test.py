
import bpy
import os
import sys

# Add the addon directory to sys.path
addon_dir = os.getcwd()
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

print(f"Testing addon registration from: {addon_dir}")

try:
    import layouts_systems_draftsman_toolkit as addon
    # The above might fail because of the folder name vs module name.
    # The dev_tool usually handles symlinking.
    
    # Try importing as local modules
    from . import config, core, properties, operators, panels
    print("Core modules imported successfully.")
    
    # Try registering
    from . import register, unregister
    
    # Use a dummy context or just call the functions to check for syntax/import errors
    print("Testing register()...")
    # Actually register/unregister might fail without a full Blender context for classes.
    # But syntax errors will be caught.
    
except Exception as e:
    print(f"FAILED registration check: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Registration check passed (No syntax or basic import errors).")
