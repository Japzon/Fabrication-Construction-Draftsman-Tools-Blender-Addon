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
import sys
import os
import traceback
import types

# Define the intended package name
PKG_NAME = 'auto_robot_cnc_dev_kit'
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

print(f"Testing environment: {ADDON_DIR}")

def setup_package():
    """Injects the addon directory into sys.modules as a package."""
    print(f"Setting up package '{PKG_NAME}' from {ADDON_DIR}...")
    
    # Create the module object
    m = types.ModuleType(PKG_NAME)
    m.__path__ = [ADDON_DIR]
    m.__file__ = os.path.join(ADDON_DIR, '__init__.py')
    m.__package__ = PKG_NAME
    sys.modules[PKG_NAME] = m
    
    # Add to sys.path so sub-imports work
    if ADDON_DIR not in sys.path:
        sys.path.append(ADDON_DIR)
    
    # Execute __init__.py
    with open(m.__file__, 'r') as f:
        code = compile(f.read(), m.__file__, 'exec')
        exec(code, m.__dict__)
    
    return m

def run_tests():
    print("\n--- Starting Add-on Integrity Test ---")
    
    # 1. Test Registration
    print("Testing Registration...")
    try:
        addon_pkg = setup_package()
        
        # In our case, the register() in __init__.py calls others
        addon_pkg.register()
        print("[SUCCESS] Registration complete.")
    except Exception as e:
        print(f"[FAILURE] Registration failed: {e}")
        traceback.print_exc()
        return

    # 2. Check Operators Visibility
    print("\nChecking Operators...")
    required_ops = [
        "lsd.execute_ai_prompt",
        "lsd.generate_preset",
        "lsd.set_joint_type",
        "lsd.calculate_center_of_mass",
        "lsd.calculate_inertia",
        "lsd.bake_mesh",
        "lsd.setup_ik"
    ]
    
    for op_id in required_ops:
        module_name, op_name = op_id.split(".")
        if hasattr(bpy.ops, module_name) and hasattr(getattr(bpy.ops, module_name), op_name):
            print(f"[OK] {op_id} is registered.")
        else:
            print(f"[MISSING] {op_id} is NOT registered.")

    # 3. Test Functional: Generate a Preset (Happy Path)
    print("\nTesting 'Generate Template' (MOBILE_BASE)...")
    try:
        # We need to set the scene property
        bpy.context.scene.lsd_pg_ai_props.robot_template = 'MOBILE_BASE'
        res = bpy.ops.lsd.generate_preset()
        if 'FINISHED' in res:
            print("[SUCCESS] Template generation finished successfully.")
        else:
            print(f"[FAILURE] Template generation returned {res}")
    except Exception as e:
        print(f"[FAILURE] Template generation crashed: {e}")
        traceback.print_exc()

    # 4. Test Joint Setting
    print("\nTesting 'Set Joint Type'...")
    try:
        armature = None
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                armature = obj
                break
        
        if armature:
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='POSE')
            if armature.pose.bones:
                # Select the bone
                for b in armature.pose.bones:
                    b.bone.select = True
                
                res = bpy.ops.lsd.set_joint_type(type='revolute')
                print(f"[SUCCESS] Set Joint Type returned {res}")
            else:
                print("[SKIP] No bones found in generated armature.")
        else:
            print("[SKIP] No armature found to test joints.")
    except Exception as e:
        print(f"[FAILURE] Set Joint Type crashed: {e}")
        traceback.print_exc()

    # 5. Check Panels
    print("\nChecking Panels...")
    # Panels are harder to check programmatically without a GUI context, 
    # but we can check if the classes are registered in bpy.types
    panel_classes = [c for c in bpy.types.Panel.__subclasses__() if c.__module__.startswith(PKG_NAME)]
    if panel_classes:
        print(f"[OK] Found {len(panel_classes)} registered panels.")
        for p in panel_classes[:5]: # Show first 5
             print(f"  - {p.bl_label}")
    else:
        print("[WARNING] No panels found matching the package name.")

    print("\n--- Test Suite Finished ---")

if __name__ == "__main__":
    run_tests()

