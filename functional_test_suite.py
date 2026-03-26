# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import bpy
import sys
import os
import traceback
import types
import time

# Define the intended package name
PKG_NAME = 'auto_robot_cnc_dev_kit'
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

def setup_package():
    """Injects the addon directory into sys.modules as a package."""
    print(f"Setting up package '{PKG_NAME}' from {ADDON_DIR}...")
    m = types.ModuleType(PKG_NAME)
    m.__path__ = [ADDON_DIR]
    m.__file__ = os.path.join(ADDON_DIR, '__init__.py')
    m.__package__ = PKG_NAME
    sys.modules[PKG_NAME] = m
    if ADDON_DIR not in sys.path:
        sys.path.append(ADDON_DIR)
    with open(m.__file__, 'r') as f:
        code = compile(f.read(), m.__file__, 'exec')
        exec(code, m.__dict__)
    return m

def run_comprehensive_tests():
    print("\n--- Starting Comprehensive Add-on Feature Test ---")
    
    try:
        addon_pkg = setup_package()
        addon_pkg.register()
        print("[SUCCESS] Registration complete.")
    except Exception as e:
        print(f"[FAILURE] Registration failed: {e}")
        traceback.print_exc()
        return

    # Helper to clear scene
    def clear_scene():
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()
        # Clear collections
        for coll in bpy.data.collections:
            if coll.name != "Collection":
                bpy.data.collections.remove(coll)

    # 1. Test AI Generation (Local)
    print("\n[TEST 1] Testing 'Generate Robot with AI' (Local)...")
    try:
        clear_scene()
        bpy.context.scene.urdf_ai_props.ai_source = 'FREE'
        bpy.context.scene.urdf_ai_props.api_prompt = "Generate a six-wheeled rover with a robotic arm"
        res = bpy.ops.urdf.execute_ai_prompt()
        if 'FINISHED' in res:
            print("[SUCCESS] AI generation finished.")
            print(f"  Objects created: {len(bpy.data.objects)}")
        else:
            print(f"[FAILURE] AI generation returned {res}")
    except Exception as e:
        print(f"[FAILURE] AI generation crashed: {e}")
        traceback.print_exc()

    # 2. Test Multiple Templates
    templates = ['ROVER', 'ARM', 'MOBILE_BASE', 'QUADRUPED']
    for t in templates:
        print(f"\n[TEST 2] Testing Template: {t}...")
        try:
            clear_scene()
            bpy.context.scene.urdf_ai_props.robot_template = t
            res = bpy.ops.urdf.generate_preset()
            if 'FINISHED' in res:
                print(f"[SUCCESS] Template {t} generated.")
            else:
                print(f"[FAILURE] Template {t} returned {res}")
        except Exception as e:
            print(f"[FAILURE] Template {t} crashed: {e}")
            traceback.print_exc()

    # 3. Test Parametric Part Creation
    print("\n[TEST 3] Testing Parametric Part Creation (GEAR/SPUR)...")
    try:
        clear_scene()
        bpy.context.scene.urdf_part_category = 'GEAR'
        bpy.context.scene.urdf_part_type = 'SPUR'
        res = bpy.ops.urdf.create_part()
        if 'FINISHED' in res:
            obj = bpy.context.active_object
            print(f"[SUCCESS] Created part: {obj.name}")
            # Test Baking
            print("  Testing Bake...")
            res_bake = bpy.ops.urdf.bake_mesh()
            if 'FINISHED' in res_bake:
                print(f"  [SUCCESS] Baked part: {bpy.context.active_object.name}")
            else:
                print(f"  [FAILURE] Bake returned {res_bake}")
        else:
            print(f"[FAILURE] Part creation returned {res}")
    except Exception as e:
        print(f"[FAILURE] Part creation/bake crashed: {e}")
        traceback.print_exc()

    # 4. Test Joint Physics/Inertia Calculations
    print("\n[TEST 4] Testing COM and Inertia Calculations...")
    try:
        clear_scene()
        # Create a basic setup: Armature + Mesh parented to bone
        bpy.ops.object.armature_add()
        rig = bpy.context.active_object
        bpy.ops.object.mode_set(mode='EDIT')
        eb = rig.data.edit_bones[0]
        eb.name = "TestBone"
        bpy.ops.object.mode_set(mode='OBJECT')
        
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0,0,1))
        cube = bpy.context.active_object
        cube.parent = rig
        cube.parent_type = 'BONE'
        cube.parent_bone = "TestBone"
        
        # Go to Pose Mode
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones["TestBone"]
        pbone.bone.select = True
        
        # Calculate COM
        res_com = bpy.ops.urdf.calculate_center_of_mass()
        print(f"  COM Calculation: {res_com}")
        print(f"  Resulting COM: {pbone.urdf_props.inertial.center_of_mass}")
        
        # Calculate Inertia
        pbone.urdf_props.collision.shape = 'BOX'
        pbone.urdf_props.inertial.mass = 1.0
        res_inertia = bpy.ops.urdf.calculate_inertia()
        print(f"  Inertia Calculation: {res_inertia}")
        print(f"  Resulting ixx: {pbone.urdf_props.inertial.ixx}")
        
    except Exception as e:
        print(f"[FAILURE] Calculation tests crashed: {e}")
        traceback.print_exc()

    # 5. Test IK Setup
    print("\n[TEST 5] Testing IK Setup...")
    try:
        # Continue from previous rig
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones["TestBone"]
        res_ik = bpy.ops.urdf.setup_ik()
        if 'FINISHED' in res_ik:
            print("[SUCCESS] IK setup finished.")
            # Check if target bone exists
            target_name = f"IK_Target_{pbone.name}"
            if target_name in rig.pose.bones:
                print(f"  Found target bone: {target_name}")
            else:
                print(f"  [FAILURE] Missing target bone: {target_name}")
        else:
            print(f"[FAILURE] IK setup returned {res_ik}")
    except Exception as e:
        print(f"[FAILURE] IK setup crashed: {e}")
        traceback.print_exc()

    print("\n--- Comprehensive Test Suite Finished ---")

if __name__ == "__main__":
    run_comprehensive_tests()

