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
import bmesh
import math
import mathutils
from typing import List, Tuple, Optional, Set, Any, Dict, Union
from . import core
from .config import (
    MOD_PREFIX, CUTTER_PREFIX, BOOL_PREFIX, WELD_THRESHOLD,
    NATIVE_SPRING_MOD_NAME, NATIVE_DAMPER_MOD_NAME, NATIVE_SLINKY_MOD_NAME
)

# ------------------------------------------------------------------------
#   BMesh Dispatcher & Regeneration Handlers
# ------------------------------------------------------------------------

def update_mesh_wrapper(self, context: bpy.types.Context):
    """
    Standard 'update' callback for parametric properties.
    Ensures changes propagate to all selected objects and follows
    the strict separation of concerns mandate.
    """
    owner_obj = self.id_data
    if not owner_obj or not hasattr(self, "is_part") or not self.is_part:
        return

    # Trigger synchronization across all selected items
    for obj in context.selected_objects:
        if obj.type == 'MESH' and hasattr(obj, "lsd_pg_mech_props"):
            if obj.lsd_pg_mech_props.is_part:
                regenerate_mech_mesh(obj, context)
                sync_part_to_bone_gizmo(obj, context)

def sync_part_to_bone_gizmo(obj: bpy.types.Object, context: bpy.types.Context):
    """Syncs the part's primary radius to the parent bone's gizmo radius."""
    if obj.parent and obj.parent_type == 'BONE' and obj.parent.type == 'ARMATURE':
        props = obj.lsd_pg_mech_props
        r = 0.05
        # Sync the radius property from the part to the bone's kinematic properties
        if props.category == 'GEAR': r = props.gear_radius
        elif props.category == 'WHEEL': r = props.wheel_radius
        elif props.category == 'PULLEY': r = props.pulley_radius
        elif props.category == 'BASIC_JOINT': r = props.joint_radius
        # AI Editor Note: CRITICAL FIX FOR KINEMATIC SCALING
        # Both 'joint_radius' properties carry 'unit=LENGTH' and are stored in METERS.
        # We must NOT apply the scene scale factor (s) when syncing values between 
        # length-based properties, otherwise we multiply the metric value by the 
        # conversion factor (e.g. 1000 for mm), resulting in massive distortions.
        # The scale factor 's' should only be used when generating MESH geometry 
        # in Blender Units (BU) or calculating GIZMO visual scales.
        pbone = obj.parent.pose.bones.get(obj.parent_bone)
        if pbone and hasattr(pbone, "lsd_pg_kinematic_props"):
            pbone.lsd_pg_kinematic_props.joint_radius = r
            if hasattr(core, 'update_single_bone_gizmo'):
                # Gizmo update handles its own internal BU scaling
                core.update_single_bone_gizmo(pbone, context.scene.lsd_viz_gizmos)

def regenerate_mech_mesh(obj: bpy.types.Object, context: bpy.types.Context):
    """The central entry point for procedural mesh construction."""
    if not obj or not hasattr(obj, "lsd_pg_mech_props") or not obj.lsd_pg_mech_props.is_part:
        return
    
    props = obj.lsd_pg_mech_props
    # 1. Non-BMesh Categories (Geometry Nodes or Curve based)
    if props.category == 'SPRING':
        update_native_spring_properties(obj, props, context)
        return
    elif props.category == 'CHAIN':
        target_obj = props.instanced_link_obj
        if target_obj:
            update_mesh_data(target_obj, context, lambda bm: generate_chain_link_mesh(bm, props))
        update_native_chain_properties(obj, props, context)
        return
    elif props.category == 'ROPE':
        update_mesh_data(obj, context, lambda bm: generate_rope_mesh(bm, props))
        update_native_rope_properties(obj, props, context)
        return

    # 2. Standard BMesh Bounding Box/Generation Categories
    update_mesh_data(obj, context, lambda bm: dispatch_generation(bm, props, obj, context))
    # --- AI Editor Note: Sub-Component Regeneration ---
    # We must also regenerate all stationary or auxiliary objects (stator, screw, etc.)
    for attr in ["joint_stator_obj", "joint_screw_obj", "joint_pin_obj"]:
        sub_obj = getattr(props, attr, None)
        if sub_obj and sub_obj.type == 'MESH':
            # Use specific generator logic for the sub-object
            update_mesh_data(sub_obj, context, lambda bm: generate_stator_mesh(bm, props, sub_obj, context))
    
    # 3. Post-generation Modifiers and Shading
    finalize_modifiers(obj, props, context)

def update_mesh_data(obj: bpy.types.Object, context: bpy.types.Context, gen_func):
    """Generic BMesh lifecycle handler ensuring memory safety and clean geometry."""
    bm = bmesh.new()
    try:
        gen_func(bm)
        if bm.verts:
            # Rule 6: Mandatory Memory Cycle & Cleaning
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_THRESHOLD)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            obj.data.clear_geometry()
            bm.to_mesh(obj.data)
            obj.data.update()
    finally:
        bm.free()

def dispatch_generation(bm: bmesh.types.BMesh, props, obj, context):
    """Dispatches to specific generator logic based on category."""
    cat = props.category
    if cat == 'GEAR': generate_gear_mesh(bm, props, obj)
    elif cat == 'RACK': generate_rack_mesh(bm, props, obj)
    elif cat == 'FASTENER': generate_fastener_mesh(bm, props, obj, context)
    elif cat == 'ELECTRONICS': generate_electronics_mesh(bm, props, obj)
    elif cat == 'WHEEL': generate_wheel_mesh(bm, props, obj)
    elif cat == 'PULLEY': generate_pulley_mesh(bm, props, obj)
    elif cat == 'BASIC_JOINT': generate_basic_joint_mesh(bm, props, obj, context)
    elif cat == 'BASIC_SHAPE': generate_basic_shape_mesh(bm, props, obj)
    elif cat == 'ARCHITECTURAL': generate_architectural_mesh(bm, props, obj)
    elif cat == 'VEHICLE': generate_vehicle_mesh(bm, props, obj)

# ------------------------------------------------------------------------
#   GENERATION LOGIC
# ------------------------------------------------------------------------

def generate_gear_mesh(bm: bmesh.types.BMesh, props, obj):
    """Procedural circular gear construction."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    teeth = max(1, props.gear_teeth_count)
    segs = teeth * 2
    # All radius and width properties carry 'unit=LENGTH' and are stored in METERS (BU).
    # We must NOT apply the scene scale factor (s) as it creates 1000x distortions.
    rad = props.gear_radius
    width = props.gear_width
    depth = props.gear_tooth_depth
    taper = props.gear_tooth_taper
    if props.type_gear == 'INTERNAL':
        outer_rad = max(props.gear_outer_radius, rad + depth + 0.05)
        mat = mathutils.Matrix.Translation((0,0,-width/2))
        res_outer = bmesh.ops.create_circle(bm, radius=outer_rad, segments=segs, matrix=mat)
        res_inner = bmesh.ops.create_circle(bm, radius=rad, segments=segs, matrix=mat)
        edges = list({e for v in res_outer['verts']+res_inner['verts'] for e in v.link_edges})
        bmesh.ops.bridge_loops(bm, edges=edges)
        res_ex = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        bmesh.ops.translate(bm, verts=[v for v in res_ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=(0,0,width))
        faces = [f for f in bm.faces if len(f.verts)==4 and abs(f.normal.z)<0.1]
    else:
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=rad, radius2=rad, depth=width, segments=segs)
        faces = [f for f in bm.faces if len(f.verts)==4 and abs(f.normal.z)<0.1]
    
    faces.sort(key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x))
    faces_to_extrude = faces[::2]
    for f in faces_to_extrude:
        ex = bmesh.ops.extrude_face_region(bm, geom=[f])
        new_f = [g for g in ex['geom'] if isinstance(g, bmesh.types.BMFace)][0]
        ext_dir = new_f.normal if props.type_gear != 'INTERNAL' else -new_f.normal
        bmesh.ops.translate(bm, verts=new_f.verts, vec=ext_dir * depth)
        c = new_f.calc_center_median()
        bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation(c) @ mathutils.Matrix.Diagonal((taper, taper, 1.0, 1.0)) @ mathutils.Matrix.Translation(-c), verts=new_f.verts)

def generate_rack_mesh(bm: bmesh.types.BMesh, props, obj):
    """Procedural rack segment construction with array setup."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    teeth = max(1, props.rack_teeth_count)
    total_l = props.rack_length
    seg_l = total_l / teeth
    w = props.rack_width
    h = props.rack_height
    d = props.rack_tooth_depth
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(seg_l, w, h))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(seg_l/2, 0, -h/2))
    top = max((f for f in bm.faces if f.normal.z > 0.5), key=lambda f: f.calc_center_median().z, default=None)
    if top:
        ex = bmesh.ops.extrude_face_region(bm, geom=[top])
        bmesh.ops.translate(bm, verts=[v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)], vec=(0,0,d))
        new_top = max((f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace) and f.normal.z > 0.1), key=lambda f: f.calc_center_median().z, default=None)
        if new_top:
            c = new_top.calc_center_median()
            bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation(c) @ mathutils.Matrix.Diagonal((props.gear_tooth_taper, 1.0, 1.0, 1.0)) @ mathutils.Matrix.Translation(-c), verts=new_top.verts)
    
    # ARRAY MODIFIER SYNC
    mod_name = f"{MOD_PREFIX}Rack_Array"
    mod = obj.modifiers.get(mod_name) or obj.modifiers.new(mod_name, 'ARRAY')
    mod.fit_type = 'FIXED_COUNT'; mod.count = teeth; mod.use_relative_offset = False; mod.use_constant_offset = True
    mod.constant_offset_displace = (seg_l, 0, 0)
    weld_name = f"{MOD_PREFIX}Rack_Weld"
    if weld_name not in obj.modifiers: obj.modifiers.new(weld_name, 'WELD').merge_threshold = WELD_THRESHOLD

def generate_fastener_mesh(bm: bmesh.types.BMesh, props, obj, context):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.fastener_radius
    l = props.fastener_length
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=l, segments=12)

def generate_electronics_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    if 'MOTOR' in props.type_electronics:
        r = props.joint_motor_radius; l = props.joint_motor_length
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=l, segments=32)
        if props.joint_motor_shaft:
            sl = props.joint_motor_shaft_length; sr = props.joint_motor_shaft_radius
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=sr, radius2=sr, depth=sl, segments=12, matrix=mathutils.Matrix.Translation((0,0,l/2+sl/2)))
    else:
        # Default box fallback
        bmesh.ops.create_cube(bm, size=0.05)

def generate_wheel_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.wheel_radius; w = props.wheel_width
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0,0,0), matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'X'))

def generate_pulley_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.pulley_radius; w = props.pulley_width
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)

def generate_stator_mesh(bm: bmesh.types.BMesh, props, obj, context):
    """Generates the stationary (base) components of a mechatronic joint."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.joint_radius; w = props.joint_width
    if props.type_basic_joint == 'JOINT_REVOLUTE':
        # Frame (Stator)
        fw = props.joint_frame_width; fl = props.joint_frame_length
        # Align frame with the eye/axis
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, -fl/2 - r, 0)) @ mathutils.Matrix.Scale(fw, 4, (1,0,0)) @ mathutils.Matrix.Scale(fl, 4, (0,1,0)) @ mathutils.Matrix.Scale(w, 4, (0,0,1)))
    
    elif props.type_basic_joint == 'JOINT_CONTINUOUS':
        # Motor Body (Stator)
        br = props.joint_base_radius; bl = props.joint_base_length
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=br, radius2=br, depth=bl, segments=32)
    
    elif props.type_basic_joint == 'JOINT_PRISMATIC':
        # Screw Shaft (Stator) - Reoriented to VERTICAL (Z)
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=16)
    
    elif 'WHEELS' in props.type_basic_joint:
        # Rack Rail (Stator) - Already Vertical (Z)
        rl = props.rack_length; rw = props.rack_width; rt = props.joint_sub_thickness
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(rt, 4, (1,0,0)) @ mathutils.Matrix.Scale(rw, 4, (0,1,0)) @ mathutils.Matrix.Scale(rl, 4, (0,0,1)))

def generate_basic_joint_mesh(bm: bmesh.types.BMesh, props, obj, context):
    """Generates the moving (rotor/carriage) components of a mechatronic joint."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.joint_radius; w = props.joint_width
    sub_s = props.joint_sub_size * s; sub_t = props.joint_sub_thickness * s
    if props.type_basic_joint == 'JOINT_REVOLUTE':
        # Eye (Cylinder)
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)
        # Pin
        pr = props.joint_pin_radius * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=pr, radius2=pr, depth=w*1.5, segments=16)
        # --- Rotor Arm Implementation ---
        al = props.rotor_arm_length * s; aw = props.rotor_arm_width * s; ah = props.rotor_arm_height * s
        # Arm extends outward from the eye (Y axis in current frame logic)
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, al/2 + r, 0)) @ mathutils.Matrix.Scale(aw, 4, (1,0,0)) @ mathutils.Matrix.Scale(al, 4, (0,1,0)) @ mathutils.Matrix.Scale(ah, 4, (0,0,1)))

    elif props.type_basic_joint == 'JOINT_CONTINUOUS':
        # Shaft Only (Rotor)
        sr = props.joint_motor_shaft_radius * s; sl = props.joint_motor_shaft_length * s
        bl = props.joint_base_length * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=sr, radius2=sr, depth=sl, segments=12, matrix=mathutils.Matrix.Translation((0,0,bl/2+sl/2)))
        # --- Rotor Arm (Optional for motors) ---
        al = props.rotor_arm_length * s; aw = props.rotor_arm_width * s; ah = props.rotor_arm_height * s
        if al > 0:
             bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, al/2 + sr, bl/2 + sl - ah/2)) @ mathutils.Matrix.Scale(aw, 4, (1,0,0)) @ mathutils.Matrix.Scale(al, 4, (0,1,0)) @ mathutils.Matrix.Scale(ah, 4, (0,0,1)))

    elif props.type_basic_joint == 'JOINT_PRISMATIC':
        # Nut Block Only (Rotor) - Influenced by moving gizmo
        # Logic: Moves along the Screw Shaft (Z)
        bmesh.ops.create_cube(bm, size=sub_s)
    
    elif props.type_basic_joint == 'JOINT_SPHERICAL':
        # Ball and Socket
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=r)
        sr = props.joint_pin_radius * s; sl = props.joint_pin_length * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=sr, radius2=sr, depth=sl, segments=12, matrix=mathutils.Matrix.Translation((0,0,r+sl/2)))

    elif 'WHEELS' in props.type_basic_joint:
        # Carriage & Wheels (Rotor)
        cw = props.joint_carriage_width * s; cl = props.joint_sub_size * s; ct = props.joint_carriage_thickness * s
        wt = props.wheel_thickness * s; wr = props.joint_radius * s
        # Carriage Plate (Vertical in XZ, moves on Z)
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(cw, 4, (1,0,0)) @ mathutils.Matrix.Scale(ct, 4, (0,1,0)) @ mathutils.Matrix.Scale(cl, 4, (0,0,1)))
        # Wheels
        for side in [-1, 1]:
            for end in [-1, 1]:
                mat = mathutils.Matrix.Translation((side * (cw/2 + wt/2), 0, end * (cl/2 - wr))) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wr, radius2=wr, depth=wt, segments=16, matrix=mat)
    else:
        # Default simple cylinder
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)

def generate_basic_shape_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    t = props.type_basic_shape
    if t == 'SHAPE_PLANE':
        sz = props.shape_size * s
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=sz/2)
    elif t == 'SHAPE_CUBE':
        lx = props.shape_length_x * s; wy = props.shape_width_y * s; hz = props.shape_height_z * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(lx, 4, (1,0,0)) @ mathutils.Matrix.Scale(wy, 4, (0,1,0)) @ mathutils.Matrix.Scale(hz, 4, (0,0,1)))
    elif t == 'SHAPE_CIRCLE':
        bmesh.ops.create_circle(bm, cap_ends=True, radius=props.shape_radius*s, segments=props.shape_vertices)
    elif t == 'SHAPE_CYLINDER':
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=props.shape_radius*s, radius2=props.shape_radius*s, depth=props.shape_height*s, segments=props.shape_vertices)
    elif t == 'SHAPE_UVSPHERE':
        bmesh.ops.create_uvsphere(bm, u_segments=props.shape_segments, v_segments=props.shape_segments//2, radius=props.shape_radius*s)
    elif t == 'SHAPE_ICOSPHERE':
        bmesh.ops.create_icosphere(bm, subdivisions=props.shape_subdivisions, radius=props.shape_radius*s)
    elif t == 'SHAPE_CONE':
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=props.shape_radius*s, radius2=0, depth=props.shape_height*s, segments=props.shape_vertices)
    elif t == 'SHAPE_TORUS':
        bmesh.ops.create_torus(bm, major_radius=props.shape_major_radius*s, minor_radius=props.shape_tube_radius*s, major_segments=props.shape_horizontal_segments, minor_segments=props.shape_vertical_segments)
    else:
        bmesh.ops.create_cube(bm, size=0.1*s)

def generate_architectural_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    raw_type = str(props.type_architectural)
    l = props.length * s; h = props.height * s
    th = props.wall_thickness * s
    if raw_type == 'BEAM':
        rad = props.radius * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(rad, 4, (0,1,0)) @ mathutils.Matrix.Scale(rad, 4, (0,0,1)))
    elif raw_type == 'WALL':
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(th, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
    elif raw_type == 'COLUMN':
        rad = props.radius * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=rad, radius2=rad, depth=h, segments=32, matrix=mathutils.Matrix.Translation((0,0,h/2)))
    elif raw_type == 'STAIRS':
        steps = max(1, props.step_count)
        rh = h / steps; td = l / steps
        for i in range(steps):
            mat = mathutils.Matrix.Translation((i * td + td/2, 0, i * rh + rh/2)) @ mathutils.Matrix.Scale(td, 4, (1,0,0)) @ mathutils.Matrix.Scale(props.wall_thickness * s, 4, (0,1,0)) @ mathutils.Matrix.Scale(rh, 4, (0,0,1))
            bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    elif raw_type == 'WINDOW' or raw_type == 'DOOR':
        ft = props.window_frame_thickness * s; gt = props.glass_thickness * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, ft/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(ft, 4, (0,0,1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h - ft/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(ft, 4, (0,0,1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((-l/2 + ft/2, 0, h/2)) @ mathutils.Matrix.Scale(ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((l/2 - ft/2, 0, h/2)) @ mathutils.Matrix.Scale(ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Scale(l - 2*ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(gt, 4, (0,1,0)) @ mathutils.Matrix.Scale(h - 2*ft, 4, (0,0,1)))
    else:
        bmesh.ops.create_cube(bm, size=0.1*s)

def generate_vehicle_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    bmesh.ops.create_cube(bm, size=1.0)

def generate_rope_mesh(bm, props):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.rope_radius * s; l = props.rope_length * s
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=l, segments=12, matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))

def generate_chain_link_mesh(bm: bmesh.types.BMesh, props):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    p = props.chain_pitch * s; r = props.chain_roller_radius * s
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=props.chain_roller_length*s, segments=16)

# ------------------------------------------------------------------------
#   POST-GENERATION HELPERS
# ------------------------------------------------------------------------

def finalize_modifiers(obj, props, context):
    if props.category == 'GEAR' and props.type_gear != 'INTERNAL' and props.gear_bore_radius > 0:
        setup_bore_hole(obj, props, context)
    else:
        m = obj.modifiers.get(f"{MOD_PREFIX}Bore")
        if m: obj.modifiers.remove(m)
        c = bpy.data.objects.get(f"{CUTTER_PREFIX}{obj.name}")
        if c: bpy.data.objects.remove(c, do_unlink=True)
    
    if props.category != 'BASIC_SHAPE':
        core.apply_auto_smooth(obj)

def setup_bore_hole(obj, props, context):
    cutter_name = f"{CUTTER_PREFIX}{obj.name}"
    cutter = bpy.data.objects.get(cutter_name)
    if not cutter:
        m = bpy.data.meshes.new(cutter_name)
        cutter = bpy.data.objects.new(cutter_name, m)
        context.collection.objects.link(cutter)
    cutter.parent = obj; cutter.hide_set(True)
    cutter.matrix_local = mathutils.Matrix.Identity(4)
    cutter.data.clear_geometry()
    u = context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=props.gear_bore_radius*s, radius2=props.gear_bore_radius*s, depth=props.gear_width*4*s, segments=32)
    bm.to_mesh(cutter.data); bm.free(); cutter.data.update()
    for p in cutter.data.polygons: p.use_smooth = True
    mod = obj.modifiers.get(f"{MOD_PREFIX}Bore") or obj.modifiers.new(name=f"{MOD_PREFIX}Bore", type='BOOLEAN')
    mod.operation = 'DIFFERENCE'; mod.solver = 'EXACT'; mod.object = cutter

# ------------------------------------------------------------------------
#   NATIVE PROPERTY SYNC
# ------------------------------------------------------------------------

def update_native_spring_properties(obj, props, context):
    u = context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0
    obj["spring_teeth"] = props.spring_turns
    obj["spring_radius"] = props.spring_radius * s
    obj["spring_wire_thickness"] = props.spring_wire_thickness * s

def update_native_chain_properties(obj, props, context):
    u = context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0
    obj["lsd_native_chain_pitch"] = props.chain_pitch * s

def update_native_rope_properties(obj, props, context):
    obj["rope_radius"] = props.rope_radius
    obj["rope_strands"] = props.rope_strands
    obj["rope_twist"] = props.twist

# ------------------------------------------------------------------------
#   DIMENSION GENERATOR UTILS
# ------------------------------------------------------------------------

def get_dimensions_collection(context):
    """Ensures the LSD_Dimensions collection exists and is visible in the current view layer."""
    coll_name = "LSD_Dimensions"
    scene_coll = context.scene.collection
    coll = bpy.data.collections.get(coll_name)
    if not coll:
        coll = bpy.data.collections.new(coll_name)
        scene_coll.children.link(coll)
    
    # AI Editor Note: Must ensure visibility on the View Layer (LayerCollection)
    # Recursively find the layer collection safely
    def find_layer_coll(root, target_name):
        if root.name == target_name: return root
        for child in root.children:
            found = find_layer_coll(child, target_name)
            if found: return found
        return None

    layer_coll = find_layer_coll(context.view_layer.layer_collection, coll_name)
    if layer_coll:
        layer_coll.hide_viewport = False
        layer_coll.exclude = False
        
    return coll

def create_triangle_anchor_mesh(name_prefix: str) -> bpy.types.Mesh:
    """
    Procedurally creates a flat triangle mesh for hook parenting.
    Oriented to point towards (0,0,0) from the +Z direction.
    """
    mesh = bpy.data.meshes.new(f"{name_prefix}_Triangle_Anchor")
    bm = bmesh.new()
    # Vertices for a triangle pointing at its own origin
    # Tip at (0,0,0), base at +Z
    v1 = bm.verts.new((0, 0.08, 0.15))
    v2 = bm.verts.new((0.069, -0.04, 0.15))
    v3 = bm.verts.new((-0.069, -0.04, 0.15))
    v_tip = bm.verts.new((0, 0, 0))
    bm.faces.new((v1, v2, v3))
    bm.faces.new((v1, v2, v_tip))
    bm.faces.new((v2, v3, v_tip))
    bm.faces.new((v3, v1, v_tip))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def create_dimension_line_mesh(name_prefix: str) -> bpy.types.Mesh:
    """Procedurally creates a basic line segment mesh for the dimension body."""
    mesh = bpy.data.meshes.new(f"{name_prefix}_Line")
    bm = bmesh.new()
    # Simple thin cylinder as the line (default 1m long along Z, 1m radius for 1:1 scaling)
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=1.0, radius2=1.0, depth=1.0, segments=12, matrix=mathutils.Matrix.Translation((0,0,0.5)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def create_arrow_mesh_data(name_prefix: str) -> bpy.types.Mesh:
    """Procedurally creates a mechatronic-style arrow head mesh."""
    mesh = bpy.data.meshes.new(f"{name_prefix}_Arrow")
    bm = bmesh.new()
    # Create cone for the tip
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=0.0, radius2=0.05, depth=0.15, segments=12, matrix=mathutils.Matrix.Translation((0,0,0.075)))
    # Create cylinder for the base
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=0.01, radius2=0.01, depth=0.1, segments=8, matrix=mathutils.Matrix.Translation((0,0,-0.05)))
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def setup_dimension_gn(obj: bpy.types.Object):
    """Sets up Dynamic Dimension Geometry Nodes for real-time length sync."""
    mod = obj.modifiers.get("Dynamic_Dimension") or obj.modifiers.new("Dynamic_Dimension", 'NODES')
    group_name = "LSD_Dynamic_Dimension"
    group = bpy.data.node_groups.get(group_name)
    if not group:
        group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
        group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        group.interface.new_socket("Length", in_out='INPUT', socket_type='NodeSocketFloat')
        group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        input_node = group.nodes.new('NodeGroupInput')
        output_node = group.nodes.new('NodeGroupOutput')
        transform_node = group.nodes.new('GeometryNodeTransform')
        join_node = group.nodes.new('GeometryNodeJoinGeometry')
        # Logic: Instance an arrow at 0 and at Length.
        # For simplicity in this procedural generator, we just pass the original mesh 
        # and transform a duplicate.
        group.links.new(input_node.outputs['Geometry'], join_node.inputs[0])
        group.links.new(input_node.outputs['Geometry'], transform_node.inputs['Geometry'])
        group.links.new(input_node.outputs['Length'], transform_node.inputs['Translation']) # Assuming Z scale/pos
        group.links.new(transform_node.outputs['Geometry'], join_node.inputs[0])
        group.links.new(join_node.outputs['Geometry'], output_node.inputs[0])
    
    mod.node_group = group

def setup_gn_for_rigid_array(path_obj: bpy.types.Object):
    """
    Sets up a reusable Geometry Nodes group for rigid object instancing along a path.
    Supported Paths: Curves (Bezier/NURBS) or Mesh Vertices.
    """
    group_name = "LSD_Rigid_Follow_Path"
    group = bpy.data.node_groups.get(group_name)
    if not group:
        group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
        # Interface setup
        group.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        group.interface.new_socket("Instance Object", in_out='INPUT', socket_type='NodeSocketObject')
        group.interface.new_socket("Spacing", in_out='INPUT', socket_type='NodeSocketFloat')
        group.interface.new_socket("Is Mesh", in_out='INPUT', socket_type='NodeSocketBool')
        group.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        
        # Node Creation
        nodes = group.nodes
        links = group.links
        
        input_node = nodes.new('NodeGroupInput')
        output_node = nodes.new('NodeGroupOutput')
        
        # 0. Polymorphic Path Conversion
        # If the input is a Mesh (Spawn Vertex), convert to curve first. 
        # If it's already a Curve, pass-through.
        m_to_c = nodes.new('GeometryNodeMeshToCurve')
        path_switch = nodes.new('GeometryNodeSwitch')
        path_switch.input_type = 'GEOMETRY'

        links.new(input_node.outputs['Geometry'], m_to_c.inputs['Mesh'])
        links.new(input_node.outputs['Is Mesh'], path_switch.inputs['Switch'])
        links.new(input_node.outputs['Geometry'], path_switch.inputs[1]) # False = Curve
        links.new(m_to_c.outputs['Curve'], path_switch.inputs[2]) # True = MeshToCurve
        
        # 1. Resample Path
        resample = nodes.new('GeometryNodeResampleCurve')
        resample.mode = 'LENGTH'
        links.new(path_switch.outputs[0], resample.inputs['Curve'])
        links.new(input_node.outputs['Spacing'], resample.inputs['Length'])
        
        # 2. Instance on Points
        instance_node = nodes.new('GeometryNodeInstanceOnPoints')
        links.new(resample.outputs['Curve'], instance_node.inputs['Points'])
        
        # 3. Handle Object Input
        # FIX: Using 'ORIGINAL' ensures the instances are snapped directly to the path
        # without being displaced by the blueprint object's world location.
        info_node = nodes.new('GeometryNodeObjectInfo')
        info_node.transform_space = 'ORIGINAL'

        links.new(input_node.outputs['Instance Object'], info_node.inputs['Object'])
        links.new(info_node.outputs['Geometry'], instance_node.inputs['Instance'])
        
        # 4. Rotation Alignment
        # Standardize on 'GeometryNodeInputTangent' for 4.5+ path following
        tangent_node = nodes.new('GeometryNodeInputTangent')

        align_node = nodes.new('FunctionNodeAlignEulerToVector')
        align_node.axis = 'X' # Assume +X is forward for the arrayed object
        links.new(tangent_node.outputs['Tangent'], align_node.inputs['Vector'])
        links.new(align_node.outputs['Rotation'], instance_node.inputs['Rotation'])
        
        # 5. Output Final Mix (Join instances with original path geometry)
        # This prevents the path from "disappearing" or being displaced visually.
        join_output = nodes.new('GeometryNodeJoinGeometry')
        links.new(path_switch.outputs[0], join_output.inputs[0]) # The original path
        links.new(instance_node.outputs['Instances'], join_output.inputs[0]) # The instances
        
        links.new(join_output.outputs['Geometry'], output_node.inputs['Geometry'])
        
    return group






def generate_smart_dimension_parametric(context, p1, p2, name="Dimension", parent_a=None, parent_b=None):
    # AI Editor Note: BLENDER 4.5+ ULTIMATE SYNC PASS
    if context.mode != 'OBJECT':
         bpy.ops.object.mode_set(mode='OBJECT')
         
    # Pass 3: Hard flush in Object Mode
    context.view_layer.update()
    context.evaluated_depsgraph_get().update()
    context.view_layer.update() 
    # Sync loop to make sure evaluated mesh is stable
    # This specifically addresses the 'give_parvert' timing issue
    def force_sync():
        context.view_layer.update()
        context.evaluated_depsgraph_get().update()
        
    force_sync()
    scene = context.scene
    coll = context.collection
    # Ensure p1 and p2 are valid world vectors
    if p1 is None or p2 is None: return None
    p1_v = mathutils.Vector((p1[0], p1[1], p1[2]))
    p2_v = mathutils.Vector((p2[0], p2[1], p2[2]))
    # AI Editor Note: Initial orientation logic MUST happen before Root creation
    direction = p2_v - p1_v
    initial_length = direction.length
    if initial_length < 0.0001: return None
    # AI Editor Note: Design Strategy - The 'Root' is an Empty that handles 
    # the coordinate system and orientation. Components are siblings.
    # Generate base structure Empty
    root = bpy.data.objects.new(f"{name}_Root", None)
    dim_coll = get_dimensions_collection(context)
    dim_coll.objects.link(root)
    # AI Editor Note: Blender doesn't have a 'NONE' display type. 
    # We use PLAIN_AXES but hide the object completely for visibility.
    root.empty_display_type = 'PLAIN_AXES'
    root.hide_viewport = True
    root.hide_render = True
    root.empty_display_size = 0.05
    # FINAL COORDINATE RESOLVE: Use a robust tracking logic to avoid singularities.
    # Root's +Z axis points from p1 toward p2.
    z_axis = direction.normalized()
    # Avoid singularity where track axis ('Z') is parallel to up reference axis ('Y')
    # by using 'X' as stabilizer for vertical or Y-heavy dimensions.
    if abs(z_axis.z) > 0.9 or abs(z_axis.y) > 0.9:
         rot_quat = z_axis.to_track_quat('Z', 'X')
    else:
         rot_quat = z_axis.to_track_quat('Z', 'Y')
    rot_mat = rot_quat.to_matrix().to_4x4()
    rot_mat.translation = p1_v
    # AI Editor Note: DUAL LOCK - Set both matrix and properties to ensure stability 
    # across Blender 4.5's asynchronous evaluation frames.
    root.matrix_world = rot_mat
    root.location = p1_v
    root.rotation_euler = rot_mat.to_euler()
    # AI Editor Note: Mandatory View Layer Sync to finalize world coordinates 
    # before we start parenting visual children.
    context.view_layer.update() 
    root["lsd_dist_vec"] = [direction.x, direction.y, direction.z]
    if parent_a: 
         root["lsd_parent_obj"] = parent_a[0]
         # Add back-pointer for UI persistence
         parent_a[0]["lsd_dim_root"] = root
    if parent_b: 
         root["lsd_slave_obj"] = parent_b[0]
         # Add back-pointer for UI persistence
         parent_b[0]["lsd_dim_root"] = root
         
    root["lsd_is_dimension_root"] = True
    
    # 2. CHAINING DYNAMICS: Root Follows P1 
    # AI Editor Note: To prevent dependency cycles while mirroring chaining support (1-2, 2-3).
    # We only apply Root constraints if the target is ALREADY a dimension component. 
    # For regular objects, the Dimension remains the MASTER (Object following Anchor).
    track_p1 = parent_a and (parent_a[0].get("lsd_is_dimension_anchor") or parent_a[0].get("lsd_is_dimension_hook"))
    track_p2 = parent_b and (parent_b[0].get("lsd_is_dimension_anchor") or parent_b[0].get("lsd_is_dimension_hook"))

    if track_p1:
         con_loc = root.constraints.new('COPY_LOCATION')
         con_loc.target = parent_a[0]
         
    if track_p2:
         con_track = root.constraints.new('TRACK_TO')
         con_track.target = parent_b[0]
         con_track.track_axis = 'TRACK_Z'
         con_track.up_axis = 'UP_Y'

    # Pass 4: Refresh coordinates before parenting visual children
    context.view_layer.update()
    
    # AI Editor Note: Cache world transformation for parenting restoration
    old_mat = root.matrix_world.copy()
    
    # 3. Create Physical Master Anchors (For Hook Linking)
    # These are hidden/small empties that NEVER drift with the offset.
    aa_master = bpy.data.objects.new(f"{name}_Anchor_START_MASTER", None)
    ab_master = bpy.data.objects.new(f"{name}_Anchor_END_MASTER", None)
    for o in [aa_master, ab_master]:
         dim_coll.objects.link(o)
         o.parent = root
         o["lsd_is_dimension_anchor"] = "MASTER"
    aa_master.location = (0, 0, 0)
    ab_master.location = (0, 0, initial_length)
    aa_master["lsd_anchor_type"] = "START"
    ab_master["lsd_anchor_type"] = "END"
    
    # 4. Create Visual Components (Offset-able)
    def create_arrowhead(suffix, rot_x):
        mesh = core.get_or_create_arrow_mesh()
        obj = bpy.data.objects.new(f"{name}_Arrow_{suffix}", mesh)
        dim_coll.objects.link(obj)
        obj.parent = root
        obj["lsd_is_dimension_anchor"] = "VISUAL"
        obj["lsd_anchor_type"] = suffix # START or END
        obj.rotation_euler = (math.radians(rot_x), 0, 0)
        return obj

    # Arrow A is at the START (local z=0). Its cone tip points in -Z (rot_x=180┬░),
    # meaning it points AWAY from p2 (outward).  But now root +Z goes p1ΓåÆp2,
    # so the cone tip at rot_x=0┬░ already points in +Z (away from centre at p1
    # end meaning INTO the dimension).  We must FLIP: START=0┬░ ΓåÆ tip at -Z ΓåÆ outward.
    # END=180┬░ ΓåÆ tip at +Z at z=initial_length ΓåÆ outward from centre at p2 end.
    arrow_a = create_arrowhead("START", 0.0)
    arrow_b = create_arrowhead("END", 180.0)
    # AI Editor Note: Design Strategy - Dedicated Hook Empty.
    # We parent mechatronic parts to this hook which NEVER scales, 
    # ensuring that visual arrow size doesn't distort the attached parts.
    hook = bpy.data.objects.new(f"{name}_EndHook", None)
    dim_coll.objects.link(hook)
    hook.parent = root
    hook["lsd_is_dimension_anchor"] = "HOOK"
    hook.empty_display_type = 'CIRCLE'
    hook.empty_display_size = 0.02
    hook.location = (0, 0, initial_length)
    # 4. Extension Lines (Drafting legs from arrowheads to objects)
    def create_ext_line(name_suffix, loc_z, offset_y, ext_type):
        mesh = create_dimension_line_mesh(f"{name}_{name_suffix}")
        obj = bpy.data.objects.new(f"{name}_{name_suffix}", mesh)
        dim_coll.objects.link(obj)
        obj.parent = root
        obj["lsd_is_extension_line"] = True
        obj["lsd_extension_type"] = ext_type
        # Start at arrowhead and point back to object
        obj.location = (0, offset_y, loc_z)
        obj.rotation_euler = (math.radians(90), 0, 0) 
        return obj

    ext_a = create_ext_line("ExtA", 0.0, scene.lsd_dim_offset, "START")
    ext_b = create_ext_line("ExtB", initial_length, scene.lsd_dim_offset, "END")
    # 5. Procedural Dimension Line (Body, Child of Root)
    line_mesh = create_dimension_line_mesh(name)
    dim_line = bpy.data.objects.new(f"{name}_Line", line_mesh)
    dim_coll.objects.link(dim_line)
    dim_line.parent = root
    dim_line["lsd_is_dimension_line"] = True
    dim_line.location = (0, 0, 0)
    # Line is 1m long, so s.z = length
    dim_line.scale = (1.0, 1.0, initial_length) 
    # 5. Label Object (FONT Curve for visibility)
    txt_curve = bpy.data.curves.new(f"{name}_Label_Curve", 'FONT')
    txt_curve.align_x = 'CENTER'
    txt_curve.align_y = 'CENTER' # Vertical centering for stable origin pivot
    txt_obj = bpy.data.objects.new(f"{name}_Label", txt_curve)
    dim_coll.objects.link(txt_obj)
    txt_obj.parent = root
    txt_obj["lsd_is_dimension"] = True
    txt_obj.rotation_euler = (math.radians(90), 0, 0)
    # Initial Properties
    # AI Editor Note: CRITICAL - update_arrow_settings and update_dimension_length
    # both resolve dim_props from ROOT (obj.parent), NOT from txt_obj itself.
    # We must write all initial values to BOTH the label's dim_props (for UI) AND
    # the root's dim_props (which the layout/sync functions actually read from).
    v_arrow = scene.lsd_dim_arrow_scale
    v_text = scene.lsd_dim_text_scale
    v_thick = scene.lsd_dim_line_thickness
    v_offset = scene.lsd_dim_offset
    v_text_offset = scene.lsd_dim_text_offset

    dim_props = txt_obj.lsd_pg_dim_props
    dim_props.length = initial_length
    dim_props.arrow_scale = v_arrow
    dim_props.text_scale = v_text
    dim_props.text_offset = v_text_offset
    dim_props.offset = v_offset
    dim_props.line_thickness = v_thick
    dim_props.font_name = getattr(scene, 'lsd_dim_font_name', 'DEFAULT')
    dim_props.font_bold = getattr(scene, 'lsd_dim_font_bold', False)
    dim_props.font_italic = getattr(scene, 'lsd_dim_font_italic', False)
    root_dim_props = root.lsd_pg_dim_props
    root_dim_props.length = initial_length
    root_dim_props.arrow_scale = v_arrow
    root_dim_props.text_scale = v_text
    root_dim_props.text_offset = dim_props.text_offset
    root_dim_props.offset = v_offset
    root_dim_props.line_thickness = v_thick
    root_dim_props.font_name = dim_props.font_name
    root_dim_props.font_bold = dim_props.font_bold
    root_dim_props.font_italic = dim_props.font_italic
    # REAL-TIME SYNC: Establish a master-slave hierarchy.
    # The dimension is the MASTER. Both hooks (meshes) are pulled/pushed 
    # as the dimension moves or changes length by constraining them to our anchors.
    def apply_dim_constraint(obj, target, suffix):
        # AI Editor Note: Chaining Cycle Prevention.
        # If the object is already a dimension component or hook, 
        # we check if it is part of our own root's master chain to avoid recursion.
        if obj.get("lsd_is_dimension_anchor") or obj.get("lsd_is_dimension_hook"):
             # If we are already following THIS object (chaining), do not pull it back
             if any(c.target == obj for c in root.constraints if hasattr(c, 'target')):
                  return None

        # Check for existing constraint to avoid fighting (Project Task 1.1.2 Stability Pass)
        for con in obj.constraints:
            if con.type == 'COPY_LOCATION' and con.target and con.target.get("lsd_is_dimension_anchor") == "MASTER":
                # If it already points to the same root, we are done
                if con.target.parent == root: return con
                # If it points to a DIFFERENT dimension, we might want to disable it?
                # For now, let's just ensure we don't stack multiple active ones.
                # We disable the old one to let the fresh one take over.
                con.enabled = False
        
        con = obj.constraints.new('COPY_LOCATION')
        con.target = target
        con.use_offset = False
        obj["lsd_is_dimension_hook"] = suffix
        return con

    if parent_a and parent_a[0]:
        apply_dim_constraint(parent_a[0], aa_master, "START")
        
    if parent_b and parent_b[0]:
        apply_dim_constraint(parent_b[0], ab_master, "END")
    
    # Pass 4: Final visual pass
    if hasattr(core, 'update_arrow_settings'):
         core.update_arrow_settings(txt_obj)
    
    # Assign Material
    # AI Editor Note: For objects that share a primitive mesh (like arrowheads), 
    # we must link the material to the OBJECT rather than the DATA. 
    # This ensures that local color changes on one dimension don't leak 
    # to all other dimensions using the same shared arrowhead mesh.
    mat = core.get_or_create_text_material(txt_obj)
    
    # 1. Label (Unique Curve) - DATA link is fine
    txt_obj.active_material = mat
    
    # 2. Arrowheads (Shared Mesh) - Force OBJECT link
    for arrow in [arrow_a, arrow_b]:
         if arrow:
             arrow.active_material = mat
             if arrow.material_slots:
                  arrow.material_slots[0].link = 'OBJECT'
    
    # 3. Lines & Extensions (Unique Meshes) - DATA link is fine
    dim_line.active_material = mat
    if ext_a: ext_a.active_material = mat
    if ext_b: ext_b.active_material = mat

    # 6. Visibility Enhancements (Drafting Style)
    # AI Editor Note: Set 'In Front' to ensure visibility even inside targets
    for o in [root, aa_master, ab_master, arrow_a, arrow_b, dim_line, txt_obj, hook, ext_a, ext_b]:
         if o:
              o.show_in_front = True
              # Make them stand out in Solid mode
              o.color = (0.0, 0.4, 1.0, 1.0) # Bright Blue
    
    # AI Editor Note: Remove dependency cycle. Root MUST NOT be parented 
    # back to any of the hooks it is constraining. The dimension is now independent.
    root.matrix_world = old_mat.copy()
    context.view_layer.update() 
    # Parent the second object/element to the EndHook (Conditional)
    if parent_b:
        obj_b, type_b, index_b = parent_b
        if obj_b:
             # Ensure depsgraph is current
             dg = context.evaluated_depsgraph_get()
             dg.update()
             context.view_layer.update()
            
    # Finalize setup visual settings
    if hasattr(core, 'update_arrow_settings'):
         # Extra Guard: Force one last layer sync to ensure child component math is World-Accurate
         context.view_layer.update()
         core.update_arrow_settings(txt_obj)
    
    # Selection Sync
    for o in context.selected_objects:
        o.select_set(False)
    txt_obj.select_set(True)
    context.view_layer.objects.active = txt_obj
    return txt_obj

def group_dimension_master_list(context, dim_objs):
    """
    Migrates provided dimensions from the work list (sidebar) into a NEW 
    persistent Grouped Set (Tool Tab).
    """
    scene = context.scene
    master = scene.lsd_dimensions_master            
    sets = scene.lsd_dimensions_grouped_sets        
    
    # AI Editor Note: Creating a NEW set for this grouping batch
    # Priority: Use the custom tracker group name if provided, else fallback to auto-counter
    name_val = scene.lsd_dim_tracker_group_name if scene.lsd_dim_tracker_group_name.strip() else f"Group {len(sets) + 1}"
    new_set = sets.add()
    new_set.name = name_val
    
    for host in dim_objs:
        new_item = new_set.items.add()
        new_item.obj = host
        
        # 1. Recover Metadata from Sidebar (Priority)
        sidebar_item = next((m for m in master if m.obj == host), None)
        if sidebar_item:
             new_item.driver_target = sidebar_item.driver_target
             new_item.ratio = sidebar_item.ratio
        
        # 2. Heuristic Driver Recovery (Fallback for Viewport-only selection)
        # If no sidebar entry exists, inspect the object's animation data to find the driver source.
        elif host.animation_data:
             for drv_info in host.animation_data.drivers:
                  if 'lsd_pg_dim_props.length' in drv_info.data_path:
                       # Find the first target object in the driver variables
                       for var in drv_info.driver.variables:
                            for target in var.targets:
                                 if target.id and target.id.get("lsd_is_dimension"):
                                      new_item.driver_target = target.id
                                      break
                            if new_item.driver_target: break
                  if new_item.driver_target: break

    # Always clear the workspace list as requested
    master.clear()
    
    # Redirect user to the Scene Properties tab as requested
    for area in bpy.context.screen.areas:
        if area.type == 'PROPERTIES':
            try:
                area.spaces.active.context = 'SCENE'
            except:
                pass
            break
            
    return {'FINISHED'}
