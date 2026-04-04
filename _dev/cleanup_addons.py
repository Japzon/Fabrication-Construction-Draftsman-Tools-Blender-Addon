import bpy
import addon_utils

old_names = [
    "layouts_systems_draftsman_toolkit_automated",
    "Fabrication_Construction_Draftsman_Tools_Blender_Addon",
    "Layouts-Systems-Draftsman-Toolkit-Addon",
    "Layouts-Systems-Draftsman-Toolkit-Addon-main",
    "Layouts-Systems-Draftsman-Toolkit-Addon-master",
    "auto_robot_cnc_dev_kit"
]

new_name = "layouts_systems_draftsman_toolkit"
new_extension_name = f"bl_ext.user_default.{new_name}"

print("\n" + "="*50)
print("  LSD ADDON REGISTRY CLEANUP")
print("="*50)

# Unregister ALL old variations to clear the 'No module named' errors
for name in old_names:
    try:
        # Check if it's currently loaded
        if name in bpy.context.preferences.addons:
            print(f"[INFO] Disabling legacy addon: {name}")
            bpy.ops.preferences.addon_disable(module=name)
    except Exception as e:
        pass # Silently fail

# Enable the current version unconditionally for development
try:
    print(f"[INFO] Ensuring addon is enabled: {new_name}")
    # Force activation using addon_utils
    addon_utils.enable(new_name, default_set=True, persistent=True)
    if new_name in bpy.context.preferences.addons:
         print(f"[SUCCESS] Draftsman extension is now ACTIVE in this Blender instance.")
    else:
         print(f"[WARNING] Failed to enable {new_name}. Manual activation may be required.")
except Exception as e:
    print(f"[ERROR] Registry activation failure: {e}")

# Save preferences only if we disabled old ones
if any(name in bpy.context.preferences.addons for name in old_names):
    bpy.ops.wm.save_userpref()
    print("\n[INFO] Cleanup finished. Blender user preferences updated.")

# Signal to the dev_tool that setup is done
print("---LSD_BLENDER_READY---")
print("="*50 + "\n")
