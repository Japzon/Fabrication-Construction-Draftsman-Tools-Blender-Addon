
import bpy
import sys
import traceback

print("="*50)
print("  LSD ADDON REGISTRATION TEST (RETRY)")
print("="*50)

# Blender version detection for Extension module path logic
import bpy
version_float = bpy.app.version[0] + bpy.app.version[1] / 10.0

addon_name = "layouts_systems_draftsman_toolkit"
if version_float >= 4.2:
    # Target the extensions namespace if it exists, fallback to legacy
    # This prevents 'No module named' errors in modern Blender versions.
    try_names = [f"bl_ext.user_default.{addon_name}", addon_name]
else:
    try_names = [addon_name]

try:
    success = False
    for name in try_names:
        try:
            print(f"Enabling addon: {name}")
            bpy.ops.preferences.addon_enable(module=name)
            print(f"\n[SUCCESS] Addon enabled as: {name}")
            success = True
            break
        except Exception:
            print(f"[INFO] Could not enable {name}, checking alternatives...")
            continue
            
    if not success:
        raise RuntimeError(f"Could not enable {addon_name} using any known path.")
        
    sys.exit(0)
    
except Exception as e:
    print("\n" + "!"*50)
    print(f"  [ERROR] REGISTRATION FAILED!")
    print("!"*50)
    traceback.print_exc()
    sys.exit(1)
