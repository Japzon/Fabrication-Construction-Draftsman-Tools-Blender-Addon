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
        if obj.type == 'MESH' and hasattr(obj, "fcd_pg_mech_props"):
            if obj.fcd_pg_mech_props.is_part:
                regenerate_mech_mesh(obj, context)
                sync_part_to_bone_gizmo(obj, context)

def sync_part_to_bone_gizmo(obj: bpy.types.Object, context: bpy.types.Context):
    """Syncs the part's primary radius to the parent bone's gizmo radius."""
    if obj.parent and obj.parent_type == 'BONE' and obj.parent.type == 'ARMATURE':
        props = obj.fcd_pg_mech_props
        r = 0.05
        # Sync the radius property from the part to the bone's kinematic properties
        if props.category == 'GEAR': r = props.gear_radius
        elif props.category == 'WHEEL': r = props.wheel_radius
        elif props.category == 'PULLEY': r = props.pulley_radius
        elif props.category == 'BASIC_JOINT': r = props.joint_radius
        
        u = context.scene.unit_settings.scale_length
        s = 1.0 / u if u > 0 else 1.0
        
        pbone = obj.parent.pose.bones.get(obj.parent_bone)
        if pbone and hasattr(pbone, "fcd_pg_kinematic_props"):
            pbone.fcd_pg_kinematic_props.joint_radius = r * s
            if hasattr(core, 'update_single_bone_gizmo'):
                core.update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)

def regenerate_mech_mesh(obj: bpy.types.Object, context: bpy.types.Context):
    """The central entry point for procedural mesh construction."""
    if not obj or not hasattr(obj, "fcd_pg_mech_props") or not obj.fcd_pg_mech_props.is_part:
        return
    
    props = obj.fcd_pg_mech_props

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
    rad = props.gear_radius * s
    width = props.gear_width * s
    depth = props.gear_tooth_depth * s
    taper = props.gear_tooth_taper

    if props.type_gear == 'INTERNAL':
        outer_rad = max(props.gear_outer_radius * s, rad + depth + 0.05*s)
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
    total_l = props.rack_length * s
    seg_l = total_l / teeth
    w = props.rack_width * s
    h = props.rack_height * s
    d = props.rack_tooth_depth * s
    
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
    r = props.fastener_radius * s
    l = props.fastener_length * s
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=l, segments=12)

def generate_electronics_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    if 'MOTOR' in props.type_electronics:
        r = props.joint_motor_radius * s; l = props.joint_motor_length * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=l, segments=32)
        if props.joint_motor_shaft:
            sl = props.joint_motor_shaft_length * s; sr = props.joint_motor_shaft_radius * s
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=sr, radius2=sr, depth=sl, segments=12, matrix=mathutils.Matrix.Translation((0,0,l/2+sl/2)))
    else:
        # Default box fallback
        bmesh.ops.create_cube(bm, size=0.05*s)

def generate_wheel_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.wheel_radius * s; w = props.wheel_width * s
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0,0,0), matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'X'))

def generate_pulley_mesh(bm: bmesh.types.BMesh, props, obj):
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.pulley_radius * s; w = props.pulley_width * s
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=32)

def generate_stator_mesh(bm: bmesh.types.BMesh, props, obj, context):
    """Generates the stationary (base) components of a mechatronic joint."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.joint_radius * s; w = props.joint_width * s

    if props.type_basic_joint == 'JOINT_REVOLUTE':
        # Frame (Stator)
        fw = props.joint_frame_width * s; fl = props.joint_frame_length * s
        # Align frame with the eye/axis
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, -fl/2 - r, 0)) @ mathutils.Matrix.Scale(fw, 4, (1,0,0)) @ mathutils.Matrix.Scale(fl, 4, (0,1,0)) @ mathutils.Matrix.Scale(w, 4, (0,0,1)))
    
    elif props.type_basic_joint == 'JOINT_CONTINUOUS':
        # Motor Body (Stator)
        br = props.joint_base_radius * s; bl = props.joint_base_length * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=br, radius2=br, depth=bl, segments=32)
    
    elif props.type_basic_joint == 'JOINT_PRISMATIC':
        # Screw Shaft (Stator) - Reoriented to VERTICAL (Z)
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=w, segments=16)
    
    elif 'WHEELS' in props.type_basic_joint:
        # Rack Rail (Stator) - Already Vertical (Z)
        rl = props.rack_length * s; rw = props.rack_width * s; rt = props.joint_sub_thickness * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(rt, 4, (1,0,0)) @ mathutils.Matrix.Scale(rw, 4, (0,1,0)) @ mathutils.Matrix.Scale(rl, 4, (0,0,1)))

def generate_basic_joint_mesh(bm: bmesh.types.BMesh, props, obj, context):
    """Generates the moving (rotor/carriage) components of a mechatronic joint."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    r = props.joint_radius * s; w = props.joint_width * s
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
        # Note: Original code was oriented differently, reorienting to vertical rack rail.
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
        # Use individual axes
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
        # Centered box
        rad = props.radius * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(rad, 4, (0,1,0)) @ mathutils.Matrix.Scale(rad, 4, (0,0,1)))
        
    elif raw_type == 'WALL':
        # Box sitting on ground, centered on XY
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(th, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
        
    elif raw_type == 'COLUMN':
        # Vertical cylinder sitting on ground
        rad = props.radius * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=rad, radius2=rad, depth=h, segments=32, matrix=mathutils.Matrix.Translation((0,0,h/2)))
        
    elif raw_type == 'STAIRS':
        # Simple procedural stairs
        steps = max(1, props.step_count)
        rh = h / steps; td = l / steps
        for i in range(steps):
            # Step box starting from origin
            mat = mathutils.Matrix.Translation((i * td + td/2, 0, i * rh + rh/2)) @ mathutils.Matrix.Scale(td, 4, (1,0,0)) @ mathutils.Matrix.Scale(props.wall_thickness * s, 4, (0,1,0)) @ mathutils.Matrix.Scale(rh, 4, (0,0,1))
            bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
            
    elif raw_type == 'WINDOW' or raw_type == 'DOOR':
        # Frame + Glass/Panel
        ft = props.window_frame_thickness * s
        gt = props.glass_thickness * s
        
        # 4 Frame bars
        # Bottom
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, ft/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(ft, 4, (0,0,1)))
        # Top
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h - ft/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(ft, 4, (0,0,1)))
        # Left
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((-l/2 + ft/2, 0, h/2)) @ mathutils.Matrix.Scale(ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
        # Right
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((l/2 - ft/2, 0, h/2)) @ mathutils.Matrix.Scale(ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(ft, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
        
        # Center Panel (Glass or Door)
        # Sitting slightly recessed? No, centered in Y.
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Scale(l - 2*ft, 4, (1,0,0)) @ mathutils.Matrix.Scale(gt, 4, (0,1,0)) @ mathutils.Matrix.Scale(h - 2*ft, 4, (0,0,1)))
    
    else:
        # Fallback
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
    obj["fcd_native_chain_pitch"] = props.chain_pitch * s

def update_native_rope_properties(obj, props, context):
    obj["rope_radius"] = props.rope_radius
    obj["rope_strands"] = props.rope_strands
    obj["rope_twist"] = props.twist

# ------------------------------------------------------------------------
#   DIMENSION GENERATOR UTILS
# ------------------------------------------------------------------------

def get_dimensions_collection(context):
    """Ensures the FCD_Dimensions collection exists and is visible in the current view layer."""
    coll_name = "FCD_Dimensions"
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
    group_name = "FCD_Dynamic_Dimension"
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

def generate_smart_dimension_parametric(context, p1, p2, name="Dimension", parent_a=None, parent_b=None):
    """
    Spawns a procedural dimension assembly using an Empty root for clean hierarchy.
    Ensures children (anchors, lines, labels) have independent scaling.
    """
    # AI Editor Note: Mandatory transition to Object Mode.
    # Procedural assembly and parenting are only stable in Object Mode.
    if context.mode != 'OBJECT':
         bpy.ops.object.mode_set(mode='OBJECT')
         
    scene = context.scene
    coll = context.collection
    
    # 1. Orientation Logic
    dist_vec = p2 - p1
    initial_length = dist_vec.length
    if initial_length < 0.001: return
    
    # AI Editor Note: Design Strategy - The 'Root' is an Empty that handles 
    # the coordinate system and orientation. Components are siblings.
    # Generate base structure Empty
    root = bpy.data.objects.new(f"{name}_Root", None)
    dim_coll = get_dimensions_collection(context)
    dim_coll.objects.link(root)
    root.empty_display_type = 'ARROWS'
    root.empty_display_size = 0.5
    root.location = p1
    root["fcd_dist_vec"] = [dist_vec.x, dist_vec.y, dist_vec.z]
    
    # AI Editor Note: Initial orientation tracks the target p2 directly with Z
    rot_quat = dist_vec.to_track_quat('Z', 'Y')
    root.rotation_mode = 'QUATERNION'
    root.rotation_quaternion = rot_quat
    
    # 2. Spawn Anchor Start (Triangle, Child of Root)
    tri_mesh = create_triangle_anchor_mesh(name)
    aa = bpy.data.objects.new(name, tri_mesh)
    dim_coll.objects.link(aa)
    aa.parent = root
    aa["fcd_is_dimension_anchor"] = "START"
    aa.location = (0, 0, 0)
    
    # 3. Spawn Anchor End (Triangle, Child of Root)
    ab = bpy.data.objects.new(f"{name}_End", tri_mesh.copy())
    dim_coll.objects.link(ab)
    ab.parent = root
    ab["fcd_is_dimension_anchor"] = "END"
    # End is at the target length, rotated 180 to point at the target
    ab.location = (0, 0, initial_length)
    ab.rotation_euler = (math.radians(180), 0, 0) # Flip to point to P2
    
    # AI Editor Note: Design Strategy - Dedicated Hook Empty.
    # We parent mechatronic parts to this hook which NEVER scales, 
    # ensuring that visual arrow size doesn't distort the attached parts.
    hook = bpy.data.objects.new(f"{name}_EndHook", None)
    dim_coll.objects.link(hook)
    hook.parent = root
    hook["fcd_is_dimension_hook"] = "END"
    hook.empty_display_type = 'CIRCLE'
    hook.empty_display_size = 0.02
    hook.location = (0, 0, initial_length)
    
    # 4. Extension Lines (Drafting legs from arrowheads to objects)
    def create_ext_line(name_suffix, loc_z, offset_y):
        mesh = create_dimension_line_mesh(f"{name}_{name_suffix}")
        obj = bpy.data.objects.new(f"{name}_{name_suffix}", mesh)
        dim_coll.objects.link(obj)
        obj.parent = root
        obj["fcd_is_extension_line"] = True
        # Start at arrowhead and point back to object
        obj.location = (0, offset_y, loc_z)
        obj.rotation_euler = (math.radians(90), 0, 0) 
        return obj

    ext_a = create_ext_line("ExtA", 0.0, scene.fcd_dim_offset)
    ext_b = create_ext_line("ExtB", initial_length, scene.fcd_dim_offset)

    # 5. Procedural Dimension Line (Body, Child of Root)
    line_mesh = create_dimension_line_mesh(name)
    dim_line = bpy.data.objects.new(f"{name}_Line", line_mesh)
    dim_coll.objects.link(dim_line)
    dim_line.parent = root
    dim_line["fcd_is_dimension_line"] = True
    dim_line.location = (0, 0, 0)
    # Line is 1m long, so s.z = length
    dim_line.scale = (1.0, 1.0, initial_length) 
    
    # 5. Label Object (FONT Curve for visibility)
    txt_curve = bpy.data.curves.new(f"{name}_Label_Curve", 'FONT')
    txt_obj = bpy.data.objects.new(f"{name}_Label", txt_curve)
    dim_coll.objects.link(txt_obj)
    txt_obj.parent = root
    txt_obj["fcd_is_dimension"] = True
    txt_obj.rotation_euler = (math.radians(90), 0, math.radians(180))
    
    # Initial Properties
    dim_props = txt_obj.fcd_pg_dim_props
    dim_props.length = initial_length
    dim_props.arrow_scale = scene.fcd_dim_arrow_scale
    dim_props.text_scale = scene.fcd_dim_text_scale
    dim_props.offset = scene.fcd_dim_offset
    dim_props.line_thickness = 0.002
    
    # Trigger initial update
    core.update_arrow_settings(txt_obj)
    
    # Assign Material
    core.get_or_create_text_material(txt_obj)
    aa.active_material = core.get_or_create_text_material(txt_obj)
    ab.active_material = aa.active_material
    dim_line.active_material = aa.active_material
    ext_a.active_material = aa.active_material
    ext_b.active_material = aa.active_material
    
    # 6. Visibility Enhancements (Drafting Style)
    # AI Editor Note: Set 'In Front' to ensure visibility even inside targets
    for o in [root, aa, ab, dim_line, txt_obj, hook, ext_a, ext_b]:
         if o:
              o.show_in_front = True
              # Make them stand out in Solid mode
              o.color = (0.0, 0.4, 1.0, 1.0) # Bright Blue
    
    if parent_a:
        obj_a, type_a, index_a = parent_a
        # AI Editor Note: Pre-parenting sync
        if obj_a.type == 'MESH':
             obj_a.data.update()
        context.view_layer.update()
        
        root.matrix_world.translation = p1
        old_mat = root.matrix_world.copy()
        
        root.parent = obj_a
        if type_a == 'VERTEX':
             root.parent_type = 'VERTEX'
             root.parent_vertices[0] = index_a
             
        # AI Editor Note: Restore world transform after parenting to maintain exact center offset
        root.matrix_parent_inverse = obj_a.matrix_world.inverted()
        root.matrix_world = old_mat
        
        context.view_layer.update()
            
    # Parent the second object to the EndHook if provided.
    # This allows the 'Length' property to actually MOVE the second part 
    # without visual arrow scaling affecting it.
    if parent_b:
        obj_b, type_b, index_b = parent_b
        if obj_b:
            # Preserve world transform during parenting
            old_matrix = obj_b.matrix_world.copy()
            obj_b.parent = hook
            if type_b == 'VERTEX':
                 # Custom vertex parenting logic for Hook
                 pass
            obj_b.matrix_world = old_matrix
            
    # Finalize setup visual settings
    if hasattr(core, 'update_arrow_settings'):
         core.update_arrow_settings(txt_obj)
    
    # AI Editor Note: Use direct selection to avoid context errors in Edit Mode.
    # bpy.ops.object.select_all(action='DESELECT') can fail if in Edit Mode.
    for o in context.selected_objects:
        o.select_set(False)
    txt_obj.select_set(True)
    context.view_layer.objects.active = txt_obj
    
    return txt_obj
