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
import re
import os
import json
import xml.etree.ElementTree as ET
import gpu
from bpy.app.handlers import persistent
from operator import itemgetter
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from typing import List, Tuple, Optional, Set, Any, Dict
from . import config
from .config import *
from . import core
from .core import urdf_prop_update, apply_auto_smooth

#   PART 3: PROPERTY GROUP DEFINITIONS
# ------------------------------------------------------------------------


def generate_chain_link_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps') -> None:
    """
    Generates the procedural mesh for a single chain link into the provided BMesh.
    """
    bm.clear()

    # --- ACTION: Get Unit Scale ---
    u = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0

    if props.type_chain == 'BELT':
        # For belts, create a simple flat segment.
        link_width = props.belt_width * s
        link_length = props.chain_pitch * s
        link_thickness = props.belt_thickness * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Diagonal((link_length, link_thickness, link_width, 1.0)))
        return

    # --- Roller Chain logic ---
    pitch = props.chain_pitch * s
    roller_radius = props.chain_roller_radius * s
    roller_length = props.chain_roller_length * s
    plate_thickness = props.chain_plate_thickness * s
    plate_height = props.chain_plate_height * s

    # Clamp values to ensure the geometry is always valid. (Already in meters, converted to BU)
    plate_height = max(plate_height, roller_radius * 2.0 * 1.05)
    plate_thickness = max(plate_thickness, 0.001 * s)
    roller_radius = max(roller_radius, 0.001 * s)
    pitch = max(pitch, 0.001 * s)
    roller_length = max(roller_length, 0.001 * s)

    half_pitch = pitch / 2.0
    plate_end_radius = plate_height / 2.0
    inner_plate_gap = roller_length
    plate_center_z = (inner_plate_gap / 2.0) + (plate_thickness / 2.0)

    # A. Create the solid "dog-bone" plate shape in a temporary BMesh.
    plate_solid_bm = bmesh.new()
    mat1 = mathutils.Matrix.Translation((-half_pitch, 0, 0))
    bmesh.ops.create_cone(plate_solid_bm, cap_ends=True, radius1=plate_end_radius, radius2=plate_end_radius, depth=plate_thickness, segments=16, matrix=mat1)
    mat2 = mathutils.Matrix.Translation((half_pitch, 0, 0))
    bmesh.ops.create_cone(plate_solid_bm, cap_ends=True, radius1=plate_end_radius, radius2=plate_end_radius, depth=plate_thickness, segments=16, matrix=mat2)

    vert_coords = [v.co.copy() for v in plate_solid_bm.verts]
    plate_solid_bm.clear()
    for co in vert_coords: plate_solid_bm.verts.new(co)
    bmesh.ops.convex_hull(plate_solid_bm, input=plate_solid_bm.verts)

    plate_solid_mesh = bpy.data.meshes.new(".temp_plate_solid")
    plate_solid_bm.to_mesh(plate_solid_mesh)
    plate_solid_bm.free()
    plate_solid_obj = bpy.data.objects.new(".temp_plate_solid", plate_solid_mesh)
    bpy.context.collection.objects.link(plate_solid_obj)

    cutter_bm = bmesh.new()
    hole_cutter_depth = plate_thickness * 1.2
    z_offset = (plate_thickness - hole_cutter_depth) / 2.0
    for sign in [-1, 1]:
        mat = mathutils.Matrix.Translation((sign * half_pitch, 0, z_offset))
        bmesh.ops.create_cone(cutter_bm, cap_ends=True, radius1=roller_radius, radius2=roller_radius, depth=hole_cutter_depth, segments=16, matrix=mat)
    
    cutter_mesh = bpy.data.meshes.new(".temp_cutter")
    cutter_bm.to_mesh(cutter_mesh)
    cutter_bm.free()
    cutter_obj = bpy.data.objects.new(".temp_cutter", cutter_mesh)
    bpy.context.collection.objects.link(cutter_obj)

    mod = plate_solid_obj.modifiers.new(name="TempBool", type='BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter_obj
    mod.solver = 'EXACT'

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    final_plate_mesh = bpy.data.meshes.new_from_object(plate_solid_obj, depsgraph=depsgraph)
    bm.from_mesh(final_plate_mesh)

    bpy.data.objects.remove(plate_solid_obj, do_unlink=True)
    bpy.data.objects.remove(cutter_obj, do_unlink=True)
    bpy.data.meshes.remove(plate_solid_mesh, do_unlink=True)
    bpy.data.meshes.remove(cutter_mesh, do_unlink=True)
    bpy.data.meshes.remove(final_plate_mesh, do_unlink=True)

    plate1_initial_verts = list(bm.verts)
    bmesh.ops.translate(bm, verts=plate1_initial_verts, vec=(0, 0, plate_center_z))
    if abs(plate_angle_rad) > 0.001:
        bmesh.ops.rotate(bm, verts=plate1_initial_verts, cent=(0, 0, plate_center_z), matrix=mathutils.Matrix.Rotation(plate_angle_rad, 3, 'X'))
 
    plate1_geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    ret: dict = bmesh.ops.duplicate(bm, geom=plate1_geom)
    plate2_verts = [v for v in ret['geom'] if isinstance(v, bmesh.types.BMVert)]
    new_faces = [f for f in ret['geom'] if isinstance(f, bmesh.types.BMFace)]
    bmesh.ops.scale(bm, verts=plate2_verts, vec=(1, 1, -1), space=mathutils.Matrix.Identity(4))
    bmesh.ops.reverse_faces(bm, faces=new_faces)

    loc = mathutils.Vector((half_pitch, 0, 0))
    rot_angle = mathutils.Matrix.Rotation(roller_angle_rad, 4, 'X')
    final_mat = mathutils.Matrix.Translation(loc) @ rot_angle
    roller_depth = inner_plate_gap
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=roller_radius, radius2=roller_radius, depth=roller_depth, segments=16, matrix=final_mat)

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bmesh.ops.triangulate(bm, faces=bm.faces)

def setup_gn_for_rigid_array(path_obj: bpy.types.Object) -> bpy.types.GeometryNodeTree:
    """
    Creates a shared, reusable Geometry Nodes group for general-purpose rigid
    array instancing along a curve.

    This function creates a single, shared node group that can be used by multiple
    "Follow Curve" modifiers in 'RIGID' mode. This is a general-purpose tool,
    distinct from the more specialized parametric chain system.

    :param path_obj: The curve object that will host the modifier.
    :return: The created or retrieved Geometry Node group.
    """
    gn_group_name = f"{MOD_PREFIX}Native_RigidArray_GN"  # Shared group for this tool
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')

        # --- Define Interface (Inputs & Outputs) ---
        iface = gn_group.interface
        iface.new_socket(name="Geometry", in_out="INPUT", socket_type='NodeSocketGeometry')
        iface.new_socket(name="Instance Object", in_out="INPUT", socket_type='NodeSocketObject')
        spacing_socket = iface.new_socket(name="Spacing", in_out="INPUT", socket_type='NodeSocketFloat')
        spacing_socket.default_value = 1.0
        spacing_socket.min_value = 0.01
        iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

        # --- Create Nodes ---
        nodes = gn_group.nodes
        links = gn_group.links

        group_input = nodes.new('NodeGroupInput')
        group_output = nodes.new('NodeGroupOutput')
        instance_info = nodes.new('GeometryNodeObjectInfo')
        instance_info.transform_space = 'ORIGINAL'
        curve_to_points = nodes.new('GeometryNodeCurveToPoints')
        curve_to_points.mode = 'LENGTH'
        align_rotation = nodes.new('FunctionNodeAlignEulerToVector')
        align_rotation.axis = 'X'  # Assumes instance mesh is oriented along X
        instance_on_points = nodes.new('GeometryNodeInstanceOnPoints')

        # --- Link Nodes ---
        links.new(group_input.outputs["Geometry"], curve_to_points.inputs['Curve'])
        links.new(group_input.outputs["Spacing"], curve_to_points.inputs['Length'])
        links.new(group_input.outputs["Instance Object"], instance_info.inputs['Object'])
        links.new(instance_info.outputs['Geometry'], instance_on_points.inputs['Instance'])
        links.new(curve_to_points.outputs['Points'], instance_on_points.inputs['Points'])
        links.new(curve_to_points.outputs['Tangent'], align_rotation.inputs['Vector'])
        links.new(align_rotation.outputs['Rotation'], instance_on_points.inputs['Rotation'])
        links.new(instance_on_points.outputs['Instances'], group_output.inputs['Geometry'])

    return gn_group

def _generate_rack_gear_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """
    Generates the procedural mesh for a single tooth segment of a rack gear.
    """
    rack_type = props.type_rack

    for mod_name in [f"{MOD_PREFIX}Rack_Array", f"{MOD_PREFIX}Rack_Weld"]:
        if mod_name in obj.modifiers:
            obj.modifiers.remove(obj.modifiers[mod_name])

    # --- AI Editor Note: Unit-Aware Generation ---
    # BMesh operations work in Blender Units (BU). We must convert our metric
    # properties to BU using the inverse of the scene's unit scale.
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0

    teeth_count = max(1, props.rack_teeth_count)
    total_len = props.rack_length * s
    seg_len = total_len / teeth_count
    width = props.rack_width * s
    base_height = props.rack_height * s
    depth = props.rack_tooth_depth * s

    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(seg_len, width, base_height))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(seg_len / 2.0, 0, -base_height / 2.0))

    margin = seg_len * props.tooth_spacing / 2.0
    margin = min(margin, seg_len * 0.49)
    
    if margin > 0.001:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(margin, 0, 0), plane_no=(-1, 0, 0))
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], plane_co=(seg_len - margin, 0, 0), plane_no=(1, 0, 0))

    top_face = max((f for f in bm.faces if f.normal.z > 0.5 and abs(f.calc_center_median().x - seg_len/2.0) < seg_len * 0.1), key=lambda f: f.calc_center_median().z, default=None)
    
    if top_face:
        r = bmesh.ops.extrude_face_region(bm, geom=[top_face])
        verts_extruded = [v for v in r['geom'] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts_extruded, vec=(0, 0, depth))

        extruded_top_face = max((f for f in r['geom'] if isinstance(f, bmesh.types.BMFace) and f.normal.z > 0.1), key=lambda f: f.calc_center_median().z, default=None)
        if extruded_top_face:
            center = extruded_top_face.calc_center_median()
            mat_scale = mathutils.Matrix.Diagonal((props.gear_tooth_taper, 1.0, 1.0, 1.0))
            bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation(center) @ mat_scale @ mathutils.Matrix.Translation(-center), verts=extruded_top_face.verts)

            if rack_type not in ['RACK_SPUR']:
                cuts = 16 if 'DOUBLE' in rack_type else 6 if 'HERRING' in rack_type else 4
                edges_y = [e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) < 0.001 and abs(e.verts[0].co.z - e.verts[1].co.z) < 0.001]
                if edges_y: bmesh.ops.subdivide_edges(bm, edges=edges_y, cuts=cuts, use_grid_fill=True)

                twist_rad = props.twist
                half_w = width / 2.0
                for v in bm.verts:
                    if rack_type == 'RACK_BEVEL' and v.co.z >= -0.001:
                        angle_rad = props.twist
                        v.co.z += (v.co.y + half_w) * math.tan(angle_rad)

                    if v.co.z > 0.001:
                        y_fac = v.co.y / half_w if half_w > 0 else 0
                        shift = 0
                        if rack_type in ['RACK_HELICAL', 'RACK_WORM']:
                            shift = math.tan(twist_rad) * v.co.y
                        elif rack_type == 'RACK_HERRINGBONE':
                            shift = math.tan(twist_rad) * (abs(v.co.y) - half_w)
                        elif rack_type == 'RACK_DOUBLE':
                            shift = math.tan(twist_rad) * (math.sin(abs(y_fac) * math.pi) * half_w)
                        
                        if abs(shift) > 0.0001:
                            v.co.x += shift

    # 6. Add modifiers to create the full rack from the single segment.
    array_mod = obj.modifiers.new(f"{MOD_PREFIX}Rack_Array", 'ARRAY')
    array_mod.fit_type = 'FIXED_COUNT'
    array_mod.use_relative_offset = False
    array_mod.use_constant_offset = True
    array_mod.count = teeth_count
    array_mod.constant_offset_displace = (seg_len, 0, 0)

    weld_mod = obj.modifiers.new(f"{MOD_PREFIX}Rack_Weld", 'WELD')
    weld_mod.merge_threshold = WELD_THRESHOLD

def _generate_circular_gear_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps') -> None:
    """
    Generates the procedural mesh for a circular gear.
    """
    # --- AI Editor Note: Unit-Aware Generation ---
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0

    gear_teeth = max(1, props.gear_teeth_count)
    segs = gear_teeth * 2
    radius = props.gear_radius * s
    length = props.gear_width * s
    depth = props.gear_tooth_depth * s

    if props.type_gear == 'INTERNAL':
        min_outer = radius + depth + 0.05 * s
        outer_rad = max(props.gear_outer_radius * s, min_outer)
        inner_rad = radius
        
        mat_bottom = mathutils.Matrix.Translation((0, 0, -length/2))
        
        ret_outer = bmesh.ops.create_circle(bm, radius=outer_rad, segments=segs, matrix=mat_bottom)
        verts_outer = ret_outer['verts']
        edges_outer = list({e for v in verts_outer for e in v.link_edges})
        
        ret_inner = bmesh.ops.create_circle(bm, radius=inner_rad, segments=segs, matrix=mat_bottom)
        verts_inner = ret_inner['verts']
        edges_inner = list({e for v in verts_inner for e in v.link_edges})
        
        bmesh.ops.bridge_loops(bm, edges=edges_outer + edges_inner)
        
        ret = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        verts_ext = [v for v in ret['geom'] if isinstance(v, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts_ext, vec=(0, 0, length))
        
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        faces_to_extrude = []
        for f in bm.faces:
            if len(f.verts) == 4 and abs(f.normal.z) < 0.1:
                center = f.calc_center_median()
                dot = f.normal.x * center.x + f.normal.y * center.y
                if dot < -0.001:
                    faces_to_extrude.append(f)
        
        faces_to_extrude.sort(key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x))
        faces_to_extrude = faces_to_extrude[::2]
    else: # External gears
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, radius1=radius, radius2=radius, depth=length, segments=segs)
        side_faces = [f for f in bm.faces if len(f.verts) == 4 and abs(f.normal.z) < 0.1]
        side_faces.sort(key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x))
        faces_to_extrude = side_faces[::2]

    if abs(props.tooth_spacing - 0.5) > 0.001:
        step_angle = math.pi / gear_teeth
        shift_angle = 0.5 * step_angle * (props.tooth_spacing - 0.5) * 2.0

        for f in faces_to_extrude:
            center = f.calc_center_median()
            center_angle = math.atan2(center.y, center.x)
            
            for v in f.verts:
                v_angle = math.atan2(v.co.y, v.co.x)
                diff = v_angle - center_angle
                if diff > math.pi: diff -= 2 * math.pi
                if diff < -math.pi: diff += 2 * math.pi
                direction = -1.0 if diff > 0 else 1.0
                rot_mat = mathutils.Matrix.Rotation(direction * shift_angle, 3, 'Z')
                v.co = rot_mat @ v.co

    for f in faces_to_extrude:
        extrude_vec_multiplier = 1.0
        new_face_geom = bmesh.ops.extrude_face_region(bm, geom=[f])
        new_face = [g for g in new_face_geom['geom'] if isinstance(g, bmesh.types.BMFace)][0]
        # Use gear_tooth_depth
        bmesh.ops.translate(bm, verts=new_face.verts, vec=new_face.normal * depth * extrude_vec_multiplier)

        center = new_face.calc_center_median()
        mat_scale = mathutils.Matrix.Diagonal((props.gear_tooth_taper, props.gear_tooth_taper, 1.0, 1.0))
        bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation(center) @ mat_scale @ mathutils.Matrix.Translation(-center), verts=new_face.verts)

    if props.type_gear == 'BEVEL':
        top_verts = [v for v in bm.verts if v.co.z > 0]
        taper_factor = math.cos(props.twist)
        bmesh.ops.transform(bm, matrix=mathutils.Matrix.Scale(taper_factor, 4, (1,0,0)) @ mathutils.Matrix.Scale(taper_factor, 4, (0,1,0)), verts=top_verts)
    elif props.type_gear in ['HELICAL', 'HERRINGBONE', 'DOUBLE_HERRING', 'WORM', 'INTERNAL']:
        cut_count = 32 if props.type_gear == 'WORM' else 6 if 'HERRING' in props.type_gear else 3
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.01], cuts=cut_count, use_grid_fill=True)

        twist_rad = props.twist
        half_h = length / 2.0
        for v in bm.verts:
            z_fac = v.co.z / half_h if half_h > 0 else 0
            angle = 0
            if props.type_gear == 'HERRINGBONE':
                angle = twist_rad * abs(z_fac)
            elif props.type_gear == 'DOUBLE_HERRING':
                angle = twist_rad * math.sin(abs(z_fac) * math.pi)
            elif props.type_gear in ['HELICAL', 'WORM', 'INTERNAL']:
                angle = twist_rad * z_fac

            if abs(angle) > 0.0001:
                v.co = mathutils.Matrix.Rotation(angle, 3, 'Z') @ v.co

def generate_gear_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates the procedural mesh for circular gears."""
    _generate_circular_gear_mesh(bm, props)

def generate_rack_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """
    Generates the procedural mesh for rack gears.
    Uses the dedicated type_rack property.
    """
    _generate_rack_gear_mesh(bm, props, obj)

def generate_fastener_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object, context: bpy.types.Context) -> None:
    """
    Generates the procedural mesh for all fastener types.
    """
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    radius = props.fastener_radius * s
    length = props.fastener_length * s

    # 1. Generate the main shaft.
    bmesh.ops.create_cone(bm, radius1=radius, radius2=radius, depth=length, segments=12, cap_ends=True)
    
    # 2. Update the head and nut cutters
    head_z = length / 2.0
    head_cutter = bpy.data.objects.get(f"{CUTTER_PREFIX}{obj.name}_Head")
    if head_cutter:
        head_bm = bmesh.new()
        if props.type_fastener == 'BOLT':
            bmesh.ops.create_cone(head_bm, cap_ends=True, radius1=radius * 1.8, radius2=radius * 1.8, depth=radius, segments=6, matrix=mathutils.Matrix.Translation((0, 0, head_z + radius / 2)))
        elif props.type_fastener == 'SCREW':
            bmesh.ops.create_cone(head_bm, cap_ends=True, radius1=radius * 2.0, radius2=radius, depth=radius * 0.8, segments=16, matrix=mathutils.Matrix.Translation((0, 0, head_z + radius * 0.4)))
        elif props.type_fastener == 'RIVET':
            overlap = radius * 0.1
            center_z = head_z - overlap
            bmesh.ops.create_uvsphere(head_bm, u_segments=32, v_segments=16, radius=radius * 1.5, matrix=mathutils.Matrix.Translation((0, 0, center_z)))
            verts_to_delete = [v for v in head_bm.verts if v.co.z < center_z - 0.001]
            bmesh.ops.delete(head_bm, geom=verts_to_delete, context='VERTS')
            edges = [e for e in head_bm.edges if e.is_boundary]
            if edges:
                bmesh.ops.edgeloop_fill(head_bm, edges=edges)
            bmesh.ops.recalc_face_normals(head_bm, faces=head_bm.faces)
        
        head_cutter.data.clear_geometry()
        head_bm.to_mesh(head_cutter.data)
        head_bm.free()
        head_cutter.data.update()

        nut_cutter = bpy.data.objects.get(f"{CUTTER_PREFIX}{obj.name}_Nut")
        nut_mod = obj.modifiers.get(f"{BOOL_PREFIX}Nut")
        is_bolt = props.type_fastener == 'BOLT'
        if nut_mod: nut_mod.show_viewport = nut_mod.show_render = is_bolt
        if is_bolt and nut_cutter:
            nut_bm = bmesh.new()
            bmesh.ops.create_cone(nut_bm, cap_ends=True, radius1=radius * 1.8, radius2=radius * 1.8, depth=radius * 0.8, segments=6, matrix=mathutils.Matrix.Translation((0, 0, -head_z - radius * 0.4)))
            nut_cutter.data.clear_geometry()
            nut_bm.to_mesh(nut_cutter.data)
            nut_bm.free()
            nut_cutter.data.update()

def generate_electronics_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates the procedural mesh for electronic components using literal properties."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    if 'MOTOR' in props.type_electronics:
        radius = props.motor_radius * s
        length = props.motor_length * s
        height = props.motor_height * s

        if props.type_electronics == 'MOTOR_DC_ROUND':
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=length, segments=32)
        elif props.type_electronics == 'MOTOR_DC_FLAT':
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=length, segments=32)
            bmesh.ops.scale(bm, vec=(1.0, 0.7, 1.0), verts=list(bm.verts))
        elif props.type_electronics == 'MOTOR_STEPPER_NEMA':
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(radius*2, 4, (1,0,0)) @ mathutils.Matrix.Scale(radius*2, 4, (0,1,0)) @ mathutils.Matrix.Scale(length, 4, (0,0,1)))
            boss_h = length * 0.05; boss_r = radius * 0.8
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=boss_r, radius2=boss_r, depth=boss_h, segments=32, matrix=mathutils.Matrix.Translation((0, 0, length/2 + boss_h/2)))
        elif props.type_electronics in ['MOTOR_SERVO_STD', 'MOTOR_SERVO_MICRO']:
            body_w = radius * 2; body_l = length; body_h = height
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(body_l, 4, (1,0,0)) @ mathutils.Matrix.Scale(body_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(body_h, 4, (0,0,1)))
            tab_l = body_l * 1.3; tab_w = body_w; tab_h = body_h * 0.1; tab_z = body_h * 0.3
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, tab_z)) @ mathutils.Matrix.Scale(tab_l, 4, (1,0,0)) @ mathutils.Matrix.Scale(tab_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(tab_h, 4, (0,0,1)))
            boss_r = body_w * 0.25; boss_h = body_h * 0.15; boss_x = body_l * 0.25
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=boss_r, radius2=boss_r, depth=boss_h, segments=24, matrix=mathutils.Matrix.Translation((boss_x, 0, body_h/2 + boss_h/2)))
        elif props.type_electronics == 'MOTOR_BLDC_OUTRUNNER':
            base_h = length * 0.2; base_r = radius * 0.4
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=base_r, radius2=base_r, depth=base_h, segments=32, matrix=mathutils.Matrix.Translation((0, 0, -length/2 + base_h/2)))
            bell_h = length * 0.75; bell_r = radius
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=bell_r, radius2=bell_r, depth=bell_h, segments=32, matrix=mathutils.Matrix.Translation((0, 0, length/2 - bell_h/2)))

        if props.motor_shaft:
            shaft_len = props.motor_shaft_length * s; shaft_rad = props.motor_shaft_radius * s
            shaft_pos = mathutils.Vector((0, 0, length/2 + shaft_len/2))
            if props.type_electronics in ['MOTOR_SERVO_STD', 'MOTOR_SERVO_MICRO']:
                shaft_pos = mathutils.Vector(((props.motor_length * s) * 0.25, 0, height/2 + height * 0.15 + shaft_len/2))
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=shaft_rad, radius2=shaft_rad, depth=shaft_len, segments=16, matrix=mathutils.Matrix.Translation(shaft_pos))

    elif 'SENSOR' in props.type_electronics:
        radius = props.sensor_radius * s; length = props.sensor_length * s; height = props.sensor_height * s
        if props.type_electronics == 'SENSOR_LIDAR':
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=length, segments=32)
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius * 0.9, radius2=radius * 0.9, depth=length * 0.6, segments=32, matrix=mathutils.Matrix.Translation((0, 0, length * 0.2)))
        elif props.type_electronics == 'SENSOR_ULTRASONIC':
            body_l = length; body_w = radius * 2; body_h = height
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(body_l, 4, (1,0,0)) @ mathutils.Matrix.Scale(body_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(body_h, 4, (0,0,1)))
            num_transducers = 2; trans_r = body_w * 0.3; trans_h = body_h * 0.4
            for i in range(num_transducers):
                mat = mathutils.Matrix.Translation((-body_l/4 + i*body_l/2, body_w/2, 0)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=trans_r, radius2=trans_r, depth=trans_h, segments=16, matrix=mat)
        elif props.type_electronics == 'SENSOR_IMU':
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(length, 4, (1,0,0)) @ mathutils.Matrix.Scale(radius*2, 4, (0,1,0)) @ mathutils.Matrix.Scale(height, 4, (0,0,1)))
        else:
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=length, segments=32)

    elif 'CAMERA' in props.type_electronics:
        body_l = props.camera_case_length * s; body_w = props.camera_case_width * s; body_h = props.camera_case_height * s
        lens_r = props.camera_lens_radius * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(body_l, 4, (1,0,0)) @ mathutils.Matrix.Scale(body_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(body_h, 4, (0,0,1)))
        lens_l = body_l * 0.4
        mat_barrel = mathutils.Matrix.Translation((body_l/2, 0, 0)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=lens_r, radius2=lens_r, depth=lens_l, segments=24, matrix=mat_barrel)

    elif 'PCB' in props.type_electronics:
        l = props.pcb_length * s; w = props.pcb_width * s; t = props.pcb_thickness * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(w, 4, (0,1,0)) @ mathutils.Matrix.Scale(t, 4, (0,0,1)))
        if props.pcb_hole_radius > 0:
            _create_pcb_standoffs(bm, l, w, t, props.pcb_hole_radius * s)

    elif 'IC' in props.type_electronics:
        l = props.ic_length * s; w = props.ic_width * s; h = props.ic_height * s
        if props.type_electronics == 'IC_MICROCHIP':
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Scale(l, 4, (1,0,0)) @ mathutils.Matrix.Scale(w, 4, (0,1,0)) @ mathutils.Matrix.Scale(h, 4, (0,0,1)))
            num_legs = max(2, props.ic_pin_count // 2); leg_w = (l * 0.8) / (num_legs * 2 - 1); leg_h = h * 0.4
            for side in [-1, 1]:
                for i in range(num_legs):
                    x_pos = (-l * 0.4) + i * ((l * 0.8) / (num_legs - 1) if num_legs > 1 else 0)
                    bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((x_pos, side * w/2, -leg_h/2)) @ mathutils.Matrix.Scale(leg_w, 4, (1,0,0)) @ mathutils.Matrix.Scale(leg_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(leg_h, 4, (0,0,1)))
        else:
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=w/2, radius2=w/2, depth=l, segments=16, matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))

def generate_wheel_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates procedural geometry for various wheel types."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    radius = max(props.wheel_radius, 0.001) * s
    width = max(props.wheel_width, 0.001) * s
    
    hub_radius = max(props.wheel_hub_radius, 0.001) * s
    hub_width = max(props.wheel_hub_length, 0.001) * s
    sub_radius = max(props.wheel_sub_radius, 0.001) * s
    sub_length = max(props.wheel_sub_length, 0.001) * s
    
    if props.type_wheel == 'WHEEL_STANDARD':
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, radius1=radius, radius2=radius, depth=width, segments=32)
        cap_faces = [f for f in bm.faces if len(f.verts) > 4 and abs(f.normal.z) > 0.5]
        
        if cap_faces:
            # Tire bevel/rounding
            tire_edges = [e for e in bm.edges if abs(e.verts[0].co.z) > width/2 * 0.9 and abs(e.verts[1].co.z) > width/2 * 0.9]
            if tire_edges:
                bmesh.ops.bevel(bm, geom=tire_edges, offset=radius*0.05, segments=2)

            cap_faces = [f for f in bm.faces if len(f.verts) > 4 and abs(f.normal.z) > 0.5]
            rim_thickness = max(0.001, radius - hub_radius)
            res = bmesh.ops.inset_region(bm, faces=cap_faces, thickness=rim_thickness, depth=0)
            
            rim_inner_faces = res['faces']
            recess_depth = (width - hub_width) / 2.0
            res_recess = bmesh.ops.inset_region(bm, faces=rim_inner_faces, thickness=0.0, depth=-recess_depth)
            
            if props.wheel_side_pattern != 'NONE':
                side_pattern_faces = res_recess['faces']
                if props.wheel_side_pattern == 'SPOKES':
                    ret_poke = bmesh.ops.poke(bm, faces=side_pattern_faces)
                    spoke_faces = [f for f in ret_poke['faces']]
                    spoke_gap = props.wheel_pattern_spacing * s
                    bmesh.ops.inset_individual(bm, faces=spoke_faces, thickness=spoke_gap, depth=0)
                    ret_ext = bmesh.ops.extrude_face_region(bm, geom=spoke_faces)
                    verts_ext = [v for v in ret_ext['geom'] if isinstance(v, bmesh.types.BMVert)]
                    verts_top = [v for v in verts_ext if v.co.z > 0]; verts_bottom = [v for v in verts_ext if v.co.z < 0]
                    if verts_top: bmesh.ops.translate(bm, verts=verts_top, vec=(0, 0, props.wheel_pattern_depth * s))
                    if verts_bottom: bmesh.ops.translate(bm, verts=verts_bottom, vec=(0, 0, -props.wheel_pattern_depth * s))
                elif props.wheel_side_pattern == 'DISH':
                    ret_poke = bmesh.ops.poke(bm, faces=side_pattern_faces)
                    for v in ret_poke['verts']:
                        direction = -1.0 if v.co.z > 0 else 1.0
                        v.co.z += direction * props.wheel_pattern_depth * s
                elif props.wheel_side_pattern == 'RINGS':
                    current_faces = side_pattern_faces
                    # AI Editor Note: Use wheel_tread_count as a proxy for ring density if needed, or fixed num.
                    num_rings = max(2, int(props.wheel_tread_count / 4))
                    for i in range(num_rings):
                        ret_inset = bmesh.ops.inset_region(bm, faces=current_faces, thickness=props.wheel_pattern_spacing * s, depth=0)
                        current_faces = ret_inset['faces']
                        if i % 2 == 0:
                            verts_top = [v for f in current_faces for v in f.verts if v.co.z > 0]; verts_bottom = [v for f in current_faces for v in f.verts if v.co.z < 0]
                            if verts_top: bmesh.ops.translate(bm, verts=list(set(verts_top)), vec=(0, 0, props.wheel_pattern_depth * s))
                            if verts_bottom: bmesh.ops.translate(bm, verts=list(set(verts_bottom)), vec=(0, 0, -props.wheel_pattern_depth * s))

        if props.wheel_tread_pattern != 'NONE':
            side_faces = [f for f in bm.faces if len(f.verts) == 4 and abs(f.normal.z) < 0.1]
            if side_faces:
                vertical_edges = list({e for f in side_faces for e in f.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > width * 0.1})
                if vertical_edges: bmesh.ops.subdivide_edges(bm, edges=vertical_edges, cuts=2, use_grid_fill=True)
                side_faces = [f for f in bm.faces if len(f.verts) == 4 and abs(f.normal.z) < 0.1]
                if props.wheel_tread_pattern == 'BLOCKS':
                    side_faces.sort(key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x))
                    faces_to_detail = side_faces[::2]
                    if faces_to_detail: bmesh.ops.inset_individual(bm, faces=faces_to_detail, thickness=radius*0.02, depth=radius*0.05)
                elif props.wheel_tread_pattern == 'GROOVES':
                    bmesh.ops.inset_individual(bm, faces=side_faces, thickness=radius*0.03, depth=radius*0.05)
                elif props.wheel_tread_pattern == 'LINES':
                    num_lines = max(1, props.wheel_tread_count)
                    width_edges = {e for f in side_faces for e in f.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.01}
                    if width_edges:
                        bmesh.ops.subdivide_edges(bm, edges=list(width_edges), cuts=num_lines)
                        new_side_faces = [f for f in bm.faces if len(f.verts) == 4 and abs(f.normal.z) < 0.1]
                        if new_side_faces: bmesh.ops.inset_individual(bm, faces=new_side_faces, thickness=radius*0.015, depth=radius*0.02)
                elif props.wheel_tread_pattern in ['V_SHAPE', 'W_SHAPE']:
                    width_edges = [e for f in side_faces for e in f.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > width * 0.9]
                    if width_edges:
                        cuts = 1 if props.wheel_tread_pattern == 'V_SHAPE' else 3
                        bmesh.ops.subdivide_edges(bm, edges=list(set(width_edges)), cuts=cuts, use_grid_fill=True)
                        surface_verts = [v for v in bm.verts if v.co.to_2d().length > radius * 0.99 and abs(v.co.z) < width/2 * 0.99]
                        segment_angle = (2 * math.pi) / 32; shift_amount = segment_angle * 0.5
                        for v in surface_verts:
                            z_fac = v.co.z / (width / 2); angle_offset = 0
                            if props.wheel_tread_pattern == 'V_SHAPE': angle_offset = (1.0 - abs(z_fac)) * shift_amount
                            elif props.wheel_tread_pattern == 'W_SHAPE': angle_offset = math.cos(z_fac * math.pi * 2) * shift_amount * 0.5
                            v.co = mathutils.Matrix.Rotation(angle_offset, 3, 'Z') @ v.co
                        new_side_faces = [f for f in bm.faces if abs(f.normal.z) < 0.2 and f.calc_center_median().to_2d().length > radius * 0.9]
                        if new_side_faces: bmesh.ops.inset_individual(bm, faces=new_side_faces, thickness=0.015, depth=radius*0.03)

    elif props.type_wheel == 'WHEEL_OFFROAD':
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=width, segments=32)
        num_treads = max(1, props.wheel_tread_count)
        for i in range(num_treads):
            angle = (i / num_treads) * 2 * math.pi
            mat = mathutils.Matrix.Rotation(angle, 4, 'Z') @ mathutils.Matrix.Translation((radius, 0, 0))
            bmesh.ops.create_cube(bm, size=1.0, matrix=mat @ mathutils.Matrix.Scale(sub_radius, 4, (1,0,0)) @ mathutils.Matrix.Scale(radius*0.3, 4, (0,1,0)) @ mathutils.Matrix.Scale(width, 4, (0,0,1)))

    elif props.type_wheel == 'WHEEL_MECANUM':
        hub_rad = radius
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=hub_rad, radius2=hub_rad, depth=width, segments=32)
        num_rollers = max(1, props.wheel_tread_count); roller_rad = sub_radius; roller_len = sub_length
        # Tilt calculations for Mecanum
        max_len = (2 * math.pi * hub_rad / num_rollers) / 0.707 * 0.95
        roller_len = min(roller_len, max_len)
        for i in range(num_rollers):
            angle = (i / num_rollers) * 2 * math.pi
            final_mat = mathutils.Matrix.Rotation(angle, 4, 'Z') @ mathutils.Matrix.Translation((hub_rad + roller_rad * 0.5, 0, 0)) @ mathutils.Matrix.Rotation(math.radians(-45), 4, 'X')
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=roller_rad, radius2=roller_rad, depth=roller_len, segments=16, matrix=final_mat)
            support_thickness = props.wheel_sub_support_thickness; support_depth = roller_rad * 1.5; support_width = roller_rad * 0.8
            for side in [-1, 1]:
                bmesh.ops.create_cube(bm, matrix=final_mat @ mathutils.Matrix.Translation((-roller_rad * 0.5, 0, side * (roller_len / 2.0))) @ (mathutils.Matrix.Scale(support_depth, 4, (1, 0, 0)) @ mathutils.Matrix.Scale(support_width, 4, (0, 1, 0)) @ mathutils.Matrix.Scale(support_thickness, 4, (0, 0, 1))))

    elif props.type_wheel == 'WHEEL_OMNI':
        hub_rad = radius
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=hub_rad, radius2=hub_rad, depth=width, segments=32)
        num_rollers = max(1, props.wheel_tread_count); num_arrays = max(1, props.wheel_sub_arrays); roller_rad = sub_radius; roller_len = sub_length; array_spacing = width / num_arrays
        for j in range(num_arrays):
            z_offset = (j - (num_arrays - 1) / 2.0) * array_spacing; angular_offset = (2 * math.pi / num_rollers) / 2.0 if j % 2 == 1 else 0
            for i in range(num_rollers):
                angle = (i / num_rollers) * 2 * math.pi + angular_offset
                tangent_vec = mathutils.Vector((-math.sin(angle), math.cos(angle), 0))
                support_thickness = props.wheel_sub_support_thickness; support_height = roller_rad * 1.5; support_len = props.wheel_sub_support_length
                for side in [-1, 1]:
                    final_support_pos = mathutils.Vector((math.cos(angle) * (hub_rad + support_height / 2.0), math.sin(angle) * (hub_rad + support_height / 2.0), z_offset)) + tangent_vec * side * (roller_len / 2.0 + support_thickness/2.0)
                    mat_scale = mathutils.Matrix.Scale(support_height, 4, (1, 0, 0)) @ mathutils.Matrix.Scale(support_thickness, 4, (0, 1, 0)) @ mathutils.Matrix.Scale(support_len, 4, (0, 0, 1))
                    bmesh.ops.create_cube(bm, matrix=mathutils.Matrix.Translation(final_support_pos) @ mathutils.Matrix.Rotation(angle, 4, 'Z') @ mat_scale)
                    final_arm_pos = mathutils.Vector((math.cos(angle) * (hub_rad + support_height), math.sin(angle) * (hub_rad + support_height), z_offset)) + tangent_vec * side * (roller_len / 2.0)
                    mat_scale_arm = mathutils.Matrix.Scale(support_thickness, 4, (1, 0, 0)) @ mathutils.Matrix.Scale(support_thickness * 2, 4, (0, 1, 0)) @ mathutils.Matrix.Scale(support_len, 4, (0, 0, 1))
                    bmesh.ops.create_cube(bm, matrix=mathutils.Matrix.Translation(final_arm_pos) @ mathutils.Matrix.Rotation(angle, 4, 'Z') @ mat_scale_arm)
                final_mat = mathutils.Matrix.Translation((math.cos(angle) * (hub_rad + roller_rad), math.sin(angle) * (hub_rad + roller_rad), z_offset)) @ mathutils.Matrix.Rotation(angle, 4, 'Z') @ mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=roller_rad, radius2=roller_rad, depth=roller_len, segments=16, matrix=final_mat)

    elif props.type_wheel == 'WHEEL_CASTER':
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius*0.8, radius2=radius*0.8, depth=radius*0.5, segments=32, matrix=mathutils.Matrix.Translation((0, 0, radius)))

    if props.type_wheel != 'WHEEL_CASTER':
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'X'))

def generate_pulley_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates procedural geometry for various pulley types."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    radius = props.pulley_radius * s
    width = props.pulley_width * s
    groove_depth = props.pulley_groove_depth * s
    
    if props.type_pulley in ['PULLEY_V', 'PULLEY_UGROOVE']:
        gen_radius = radius + groove_depth
    else:
        gen_radius = radius
    
    if props.type_pulley == 'PULLEY_TIMING':
        num_teeth = max(10, props.pulley_teeth_count)
        gen_segments = num_teeth * 2
    else:
        gen_segments = 64
        
    bmesh.ops.create_cone(bm, cap_ends=True, radius1=gen_radius, radius2=gen_radius, depth=width, segments=gen_segments)
    
    if props.type_pulley == 'PULLEY_FLAT':
        flange_h = groove_depth
        flange_w = width * 0.1
        for z_dir in [-1, 1]:
            mat = mathutils.Matrix.Translation((0, 0, z_dir * (width/2 - flange_w/2)))
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius+flange_h, radius2=radius+flange_h, depth=flange_w, segments=64, matrix=mat)
    elif props.type_pulley == 'PULLEY_V':
        side_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > width * 0.8]
        if side_edges: bmesh.ops.subdivide_edges(bm, edges=side_edges, cuts=16)
        gw = width * 0.8; bw = width * 0.1
        for v in bm.verts:
            z_abs = abs(v.co.z)
            if z_abs < bw / 2:
                factor = radius / gen_radius
                v.co.x *= factor; v.co.y *= factor
            elif z_abs < gw / 2:
                t = (z_abs - bw/2) / (gw/2 - bw/2)
                r = radius + (gen_radius - radius) * t
                factor = r / gen_radius
                v.co.x *= factor; v.co.y *= factor
    elif props.type_pulley == 'PULLEY_UGROOVE':
        side_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > width * 0.8]
        if side_edges: bmesh.ops.subdivide_edges(bm, edges=side_edges, cuts=16)
        gw = width * 0.8
        for v in bm.verts:
            z_abs = abs(v.co.z)
            if z_abs < gw / 2:
                t = z_abs / (gw / 2)
                depth_factor = math.sqrt(max(0, 1 - t*t))
                r = gen_radius - (groove_depth * depth_factor)
                factor = r / gen_radius
                v.co.x *= factor; v.co.y *= factor
    elif props.type_pulley == 'PULLEY_TIMING':
        side_faces = [f for f in bm.faces if len(f.verts) == 4 and abs(f.normal.z) < 0.1]
        side_faces.sort(key=lambda f: math.atan2(f.calc_center_median().y, f.calc_center_median().x))
        faces_to_extrude = side_faces[::2]
        if faces_to_extrude:
            ret = bmesh.ops.extrude_face_region(bm, geom=faces_to_extrude)
            for v in [v for v in ret['geom'] if isinstance(v, bmesh.types.BMVert)]:
                dir = v.co.copy(); dir.z = 0
                if dir.length > 0.0001:
                    dir.normalize()
                    v.co += dir * groove_depth

        # AI Editor Note: Optional - Add flanges for timing pulleys as they often have them.
        # But per current spec, we just fix the teeth.

    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    radius = props.rope_radius * s
    length = props.rope_length * s
    
    if props.type_rope == 'ROPE_TUBE':
        # Use a reasonable default for wall thickness (20% of radius or linked to PCB thickness for hobby scale)
        wall_thickness = props.pcb_thickness if props.pcb_thickness > 0 else radius * 0.2
        if wall_thickness >= radius: wall_thickness = radius * 0.9
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=length, segments=32)
        # Shift origin to center
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0,0,0), matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))
        # Note: Hollow tube logic omitted here for simplicity in bmesh ops create_cone, 
        # but could be added with a cylinder subtraction.
    elif props.type_rope in ['ROPE_STEEL', 'ROPE_SYNTHETIC']:
        num_strands = max(1, props.rope_strands)
        strand_radius = radius / 2.5
        for i in range(num_strands):
            angle = (i / num_strands) * 2 * math.pi
            y = math.cos(angle) * (radius * 0.6)
            z = math.sin(angle) * (radius * 0.6)
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=strand_radius, radius2=strand_radius, depth=length, segments=12, matrix=mathutils.Matrix.Translation((0, y, z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))
        
        # Apply twist for realistic rope look
        if abs(props.twist) > 0.001:
            edges_long = [e for e in bm.edges if abs(e.verts[0].co.x - e.verts[1].co.x) > length * 0.1]
            if edges_long:
                bmesh.ops.subdivide_edges(bm, edges=edges_long, cuts=max(4, int(length * 10)), use_grid_fill=True)
            for v in bm.verts:
                v.co = mathutils.Matrix.Rotation(((v.co.x + length/2) / length) * props.twist * 5.0, 3, 'X') @ v.co

def _create_pcb_standoffs(bm, l, w, h, r):
    """Helper to create 4 corner standoffs for PCBs."""
    offset_x = l / 2.0 - r * 1.5
    offset_y = w / 2.0 - r * 1.5
    for x in [-offset_x, offset_x]:
        for y in [-offset_y, offset_y]:
            mat = mathutils.Matrix.Translation((x, y, h/2))
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=h*1.2, segments=12, matrix=mat)

def generate_basic_joint_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object, context: bpy.types.Context) -> None:
    """
    Generates procedural geometry for basic robotic joint templates.
    These meshes serve as detailed visual templates and kinematic guides, aligned to standard URDF axes (Z-axis).
    """
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    radius = max(props.joint_radius, 0.001) * s
    length = max(props.joint_width, 0.001) * s
    
    # Specific properties for joint details
    # AI Editor Note: Using new simplified and clearer property names.
    sub_size = max(props.joint_sub_size, 0.001) * s
    sub_thick = max(props.joint_sub_thickness, 0.001) * s
    pin_rad = max(props.joint_pin_radius, 0.001) * s
    pin_len = max(props.joint_pin_length, 0.001) * s
    frame_w = max(props.joint_frame_width, 0.001) * s
    frame_l = max(props.joint_frame_length, 0.001) * s
    # AI Editor Note: Read new rotor arm properties for independent control
    rotor_len = max(props.rotor_arm_length, 0.001) * s
    rotor_w = max(props.rotor_arm_width, 0.001) * s
    rotor_h = max(props.rotor_arm_height, 0.001) * s

    # --- AI Editor Note: Stator Object Management ---
    # Ensure a separate object exists for the static part of the joint.
    stator_obj = props.joint_stator_obj
    if not stator_obj:
        # Create the stator object if it doesn't exist
        mesh_name = f"{obj.name}_Stator_Mesh"
        obj_name = f"{obj.name}_Stator"
        stator_mesh = bpy.data.meshes.new(mesh_name)
        stator_obj = bpy.data.objects.new(obj_name, stator_mesh)
        
        # Link to the same collection as the main object
        for col in obj.users_collection:
            if stator_obj.name not in col.objects:
                col.objects.link(stator_obj)
        
        props.joint_stator_obj = stator_obj
        
        # Initial parenting setup: Parent to the same armature if possible, but as a root object
        # so it doesn't move with the joint bone.
        if obj.parent and obj.parent.type == 'ARMATURE':
            stator_obj.parent = obj.parent
            stator_obj.matrix_world = obj.matrix_world
        else:
            # AI Editor Note: Ensure stator spawns at the same location as the main object (cursor).
            # Explicitly copy transform components to avoid stale matrix_world on new objects.
            stator_obj.location = obj.location
            stator_obj.rotation_euler = obj.rotation_euler
            stator_obj.scale = obj.scale

    # --- AI Editor Note: Pin Object Management (for Revolute Joints) ---
    # Ensure a separate object exists for the pin, matching the XML structure.
    pin_obj = props.joint_pin_obj
    if props.type_basic_joint == 'JOINT_REVOLUTE' and not pin_obj:
        mesh_name = f"{obj.name}_Pin_Mesh"
        obj_name = f"{obj.name}_Pin"
        pin_mesh = bpy.data.meshes.new(mesh_name)
        pin_obj = bpy.data.objects.new(obj_name, pin_mesh)
        
        for col in obj.users_collection:
            if pin_obj.name not in col.objects:
                col.objects.link(pin_obj)
        
        props.joint_pin_obj = pin_obj
        
        if obj.parent and obj.parent.type == 'ARMATURE':
            pin_obj.parent = obj.parent
            pin_obj.matrix_world = obj.matrix_world
        else:
            pin_obj.location = obj.location
            pin_obj.rotation_euler = obj.rotation_euler
            pin_obj.scale = obj.scale

    # --- AI Editor Note: Screw Object Management (for Prismatic Joints) ---
    # Ensure a separate object exists for the rotating screw part of the joint.
    screw_obj = props.joint_screw_obj
    if props.type_basic_joint == 'JOINT_PRISMATIC' and not screw_obj:
        mesh_name = f"{obj.name}_Screw_Mesh"
        obj_name = f"{obj.name}_Screw"
        screw_mesh = bpy.data.meshes.new(mesh_name)
        screw_obj = bpy.data.objects.new(obj_name, screw_mesh)
        
        for col in obj.users_collection:
            if screw_obj.name not in col.objects:
                col.objects.link(screw_obj)
        
        props.joint_screw_obj = screw_obj
        
        if obj.parent and obj.parent.type == 'ARMATURE':
            screw_obj.parent = obj.parent
            screw_obj.matrix_world = obj.matrix_world
        else:
            screw_obj.location = obj.location
            screw_obj.rotation_euler = obj.rotation_euler
            screw_obj.scale = obj.scale

    # Prepare BMesh for Stator
    bm_stator = bmesh.new()
    bm_pin = bmesh.new()
    
    # --- AI Editor Note: New Revolute Joint Mesh ---
    # This mesh represents two frames connected by a rotating joint, as requested.
    if props.type_basic_joint == 'JOINT_REVOLUTE':
        # --- AI Editor Note: Reworked Clevis Joint Geometry based on XML Reference ---
        # The reference XML suggests a structure with a stator (frame), a pin, and a rotor.
        # We will generate these components to match the expected structure for a standard revolute joint.
        
        # 1. Stator (Frame) Generation -> bm_stator
        # The stator is the fixed U-bracket or frame that holds the pin.
        
        # Dimensions from properties
        gap = length  # The gap between the stator arms where the rotor fits
        arm_thick = sub_thick
        base_width = frame_w
        base_len = frame_l
        
        # Create the two side arms of the stator
        for z_dir in [-1, 1]:
            z_pos = z_dir * (gap / 2.0 + arm_thick / 2.0)
            
            # Side Arm (Box)
            # Centered at the pivot (0,0) in Y/Z, extending back in -X
            mat_arm = mathutils.Matrix.Translation((-base_len / 2.0, 0, z_pos))
            bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_arm @ mathutils.Matrix.Scale(base_len, 4, (1,0,0)) @ mathutils.Matrix.Scale(base_width, 4, (0,1,0)) @ mathutils.Matrix.Scale(arm_thick, 4, (0,0,1)))
            
            # Rounded End (Cylinder) at the pivot
            mat_cyl = mathutils.Matrix.Translation((0, 0, z_pos))
            bmesh.ops.create_cone(bm_stator, cap_ends=True, radius1=base_width/2.0, radius2=base_width/2.0, depth=arm_thick, segments=32, matrix=mat_cyl)

        # Create the connecting base plate
        # Connects the two arms at the back (-X)
        base_plate_x = -base_len
        total_height = gap + 2 * arm_thick
        mat_base = mathutils.Matrix.Translation((base_plate_x, 0, 0))
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_base @ mathutils.Matrix.Scale(arm_thick, 4, (1,0,0)) @ mathutils.Matrix.Scale(base_width, 4, (0,1,0)) @ mathutils.Matrix.Scale(total_height, 4, (0,0,1)))
        
        # 2. Rotor (Moving Part) Generation -> bm (The main object)
        # AI Editor Note: Simplified rotor generation to use direct BMesh creation.
        # The previous "Boolean Union with Temp Objects" approach was unstable during property updates.
        
        # Create Eye (The central hub)
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=radius, radius2=radius, depth=gap * 0.95, segments=32)
        
        # Create Arm (The part extending outwards)
        mat_arm = mathutils.Matrix.Translation((rotor_len / 2.0, 0, 0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat_arm @ mathutils.Matrix.Scale(rotor_len, 4, (1,0,0)) @ mathutils.Matrix.Scale(rotor_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(rotor_h, 4, (0,0,1)))
        
        # Note: These two parts overlap. This is robust for all Blender contexts and update callbacks.

        # 3. Pin Generation -> bm_pin (Separate Object)
        # The pin is now a separate object, as per the XML structure.
        pin_total_len = total_height + sub_size # Stick out slightly
        bmesh.ops.create_cone(bm_pin, cap_ends=True, radius1=pin_rad, radius2=pin_rad, depth=pin_total_len, segments=16)

    elif props.type_basic_joint == 'JOINT_CONTINUOUS':
        # Motor / Actuator Style
        # AI Editor Note: Shifted to spawn ON the grid (Base at Z=0) instead of buried.
        # Pivot point remains at the top of the body (shaft start).
        
        # 1. Motor Body (Stator) -> bm_stator
        body_len = length
        mat_body = mathutils.Matrix.Translation((0, 0, body_len/2))
        bmesh.ops.create_cone(bm_stator, cap_ends=True, radius1=radius, radius2=radius, depth=body_len, segments=32, matrix=mat_body)
        
        # 3. Output Shaft (Rotor) -> bm
        shaft_len = pin_len
        shaft_rad = pin_rad
        mat_shaft = mathutils.Matrix.Translation((0, 0, body_len + shaft_len/2))
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=shaft_rad, radius2=shaft_rad, depth=shaft_len, segments=16, matrix=mat_shaft)

        # 4. Keyway/Flat on shaft (Visual indicator of rotation)
        key_w = shaft_rad * 0.5
        key_l = shaft_len * 0.8
        mat_key = mathutils.Matrix.Translation((shaft_rad, 0, body_len + shaft_len/2))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat_key @ mathutils.Matrix.Scale(key_w, 4, (1,0,0)) @ mathutils.Matrix.Scale(key_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(key_l, 4, (0,0,1)))
        
    elif props.type_basic_joint == 'JOINT_PRISMATIC':
        # Ball Screw Style (Cube driven by cylindrical screw)
        # Aligned along Z-axis (Motion Axis).
        # The Screw is now a separate rotating part (screw_obj).
        
        # 1. Screw Shaft (Screw Object) -> bm_screw
        bm_screw = bmesh.new()
        screw_len = length
        screw_rad = radius
        bmesh.ops.create_cone(bm_screw, cap_ends=True, radius1=screw_rad, radius2=screw_rad, depth=screw_len, segments=16)
        
        # 2. Motor Mount / End Blocks (Stator) -> bm_stator
        block_size = screw_rad * 4.0
        block_h = screw_rad * 3.0
        
        # Bottom Block (Motor Mount)
        mat_bot = mathutils.Matrix.Translation((0, 0, -screw_len/2 - block_h/2))
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_bot @ mathutils.Matrix.Scale(block_size, 4, (1,0,0)) @ mathutils.Matrix.Scale(block_size, 4, (0,1,0)) @ mathutils.Matrix.Scale(block_h, 4, (0,0,1)))
        
        # Top Block (Bearing)
        mat_top = mathutils.Matrix.Translation((0, 0, screw_len/2 + block_h/2))
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_top @ mathutils.Matrix.Scale(block_size, 4, (1,0,0)) @ mathutils.Matrix.Scale(block_size, 4, (0,1,0)) @ mathutils.Matrix.Scale(block_h, 4, (0,0,1)))

        # 3. Nut Block / Carriage (Rotor) -> bm
        nut_size = sub_size
        if nut_size < screw_rad * 3.0: nut_size = screw_rad * 3.0
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Scale(nut_size, 4, (1,0,0)) @ mathutils.Matrix.Scale(nut_size, 4, (0,1,0)) @ mathutils.Matrix.Scale(nut_size, 4, (0,0,1)))

        # --- Finalize Screw Mesh ---
        if screw_obj and bm_screw.verts:
            apply_auto_smooth(screw_obj)
            bmesh.ops.remove_doubles(bm_screw, verts=bm_screw.verts, dist=0.0001)
            bmesh.ops.recalc_face_normals(bm_screw, faces=bm_screw.faces)
            screw_obj.data.clear_geometry()
            bm_screw.to_mesh(screw_obj.data)
        
        bm_screw.free()

    elif props.type_basic_joint == 'JOINT_PRISMATIC_WHEELS':
        # Rack and Wheels Style
        # 1. Rack (Stator) -> bm_stator

        # AI Editor Note: Swapped Width and Thickness mapping per user request.
        # Scale X (World Z) -> Length (props.rack_length)
        # Scale Y (World X) -> Thickness (props.chain_pitch)
        # Scale Z (World Y) -> Width (props.rack_width)
        
        rack_len_z = max(props.rack_length, 0.001)
        rack_thick_x = max(props.chain_pitch, 0.001)      # Thickness along World X
        rack_width_y = max(props.rack_width, 0.001)  # Width along World Y
        
        # AI Editor Note: Rotated stator Z 90 then X 90 per user request.
        # Matrix: Rot(90, X) @ Rot(90, Z)
        # Local X -> World Z (Length)
        # Local Y -> World -X (Thickness)
        # Local Z -> World -Y (Width)
        mat_rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Z')
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_rot @ mathutils.Matrix.Scale(rack_len_z, 4, (1,0,0)) @ mathutils.Matrix.Scale(rack_thick_x, 4, (0,1,0)) @ mathutils.Matrix.Scale(rack_width_y, 4, (0,0,1)))
        
        # 2. Carriage Plate (Rotor) -> bm
        carr_len = sub_size
        carr_w = props.joint_carriage_width
        carr_thick = props.joint_carriage_thickness
        
        # AI Editor Note: Carriage gap is now fixed/minimal to keep rack sticked to carriage.
        carr_gap = 0.001
        # AI Editor Note: Carriage position decoupled from rack thickness (X). Now depends on rack width (Y).
        # rack_width_y corresponds to the dimension along World Y.
        carr_inner_y = (rack_width_y / 2.0) + carr_gap
        carr_y_pos = carr_inner_y + (carr_thick / 2.0)
        
        mat_carr = mathutils.Matrix.Translation((0, carr_y_pos, 0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat_carr @ mathutils.Matrix.Scale(carr_w, 4, (1,0,0)) @ mathutils.Matrix.Scale(carr_thick, 4, (0,1,0)) @ mathutils.Matrix.Scale(carr_len, 4, (0,0,1)))
        
        # 3. Wheels (Rotor) -> bm
        wheel_rad = radius
        wheel_width = props.wheel_thickness # AI Editor Note: Using new wheel thickness property
        axle_len = props.wheel_axle_length
        
        # AI Editor Note: Axle anchored to carriage, extending towards rack.
        # Wheels positioned at the end of the axle.
        for x_sign in [-1, 1]: # Left/Right
            for z_sign in [-1, 1]: # Top/Bottom
                # Axle Position
                # Horizontal distance based on Rack Thickness (Stator X), not Carriage Width.
                # AI Editor Note: Use radius for X-offset to prevent overlap (Wheel Axis is Y).
                # rack_thick_x is the Thickness (World X).
                axle_x = x_sign * (rack_thick_x/2 + wheel_rad + 0.002)
                axle_z = z_sign * (carr_len/2 - wheel_rad)
                
                # Axle anchored to Carriage Inner Y, extending downwards (towards rack/origin)
                axle_center_y = carr_inner_y - (axle_len / 2.0)
                
                mat_axle = mathutils.Matrix.Translation((axle_x, axle_center_y, axle_z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wheel_rad*0.2, radius2=wheel_rad*0.2, depth=axle_len, segments=8, matrix=mat_axle)
                
                # Wheel at the end of the axle (furthest from carriage)
                wheel_y = carr_inner_y - axle_len
                mat_wheel = mathutils.Matrix.Translation((axle_x, wheel_y, axle_z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wheel_rad, radius2=wheel_rad, depth=wheel_width, segments=16, matrix=mat_wheel)

    elif props.type_basic_joint == 'JOINT_PRISMATIC_WHEELS_ROT':
        # Rack and Wheels Style (Rotated Carriage)
        # 1. Rack (Stator) -> bm_stator
        rack_len = max(props.rack_length, 0.001)
        # AI Editor Note: Rack dimensions decoupled from carriage dimensions per user request.
        rack_width_y = max(props.rack_width, 0.001)
        rack_thick_x = max(props.rack_height, 0.001)
        
        # AI Editor Note: Rack origin moved to the face closest to carriage (X=0), extending to +X.
        # This ensures correct proportioning relative to the carriage.
        mat_rack = mathutils.Matrix.Translation((rack_thick_x / 2.0, 0, 0)) @ mathutils.Matrix.Scale(rack_thick_x, 4, (1,0,0)) @ mathutils.Matrix.Scale(rack_width_y, 4, (0,1,0)) @ mathutils.Matrix.Scale(rack_len, 4, (0,0,1))
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_rack)
        
        # 2. Carriage Plate (Rotor) -> bm
        carr_len = sub_size
        carr_w = props.joint_carriage_width
        carr_thick = props.joint_carriage_thickness
        
        # AI Editor Note: Carriage distance adjusted to clear wheels per user request.
        wheel_rad = radius
        carr_gap = wheel_rad * 2.2 + 0.002
        carr_dist = carr_gap
        carr_y_pos = carr_dist + (carr_thick / 2.0)
        
        # AI Editor Note: Rotate carriage 90 degrees around Z (along base gizmo)
        # Position moves from (0, y, 0) to (-y, 0, 0)
        mat_carr_rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'Z')
        mat_carr_trans = mathutils.Matrix.Translation((0, carr_y_pos, 0))
        mat_carr = mat_carr_rot @ mat_carr_trans
        
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat_carr @ mathutils.Matrix.Scale(carr_w, 4, (1,0,0)) @ mathutils.Matrix.Scale(carr_thick, 4, (0,1,0)) @ mathutils.Matrix.Scale(carr_len, 4, (0,0,1)))
        
        # 3. Wheels & Frame (Rotor) -> bm
        # wheel_rad defined above
        wheel_width = props.wheel_thickness
        # AI Editor Note: Axle length set to rack width so wheels sit flush with the edge (inwards).
        axle_len = rack_width_y
        
        for x_sign in [-1, 1]: # Left/Right
            for z_sign in [-1, 1]: # Top/Bottom
                # Axle Position
                # AI Editor Note: Wheels now respect rack thickness and origin shift.
                offset = wheel_rad + 0.002
                axle_x = (rack_thick_x / 2.0) + x_sign * (rack_thick_x / 2.0 + offset)
                
                axle_z = z_sign * (carr_len/2 - wheel_rad)
                
                # Axle
                mat_axle = mathutils.Matrix.Translation((axle_x, 0, axle_z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wheel_rad*0.15, radius2=wheel_rad*0.15, depth=axle_len, segments=8, matrix=mat_axle)
                
                # Axle Landing (Spacer)
                landing_len = wheel_width * 0.5
                mat_landing = mathutils.Matrix.Translation((axle_x, 0, axle_z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wheel_rad*0.25, radius2=wheel_rad*0.25, depth=landing_len, segments=8, matrix=mat_landing)

                # Wheels & Supports
                for y_sign in [-1, 1]:
                    wheel_y = y_sign * (axle_len / 2.0 - wheel_width / 2.0)
                    
                    mat_wheel = mathutils.Matrix.Translation((axle_x, wheel_y, axle_z)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                    bmesh.ops.create_cone(bm, cap_ends=True, radius1=wheel_rad, radius2=wheel_rad, depth=wheel_width, segments=16, matrix=mat_wheel)
                    
                    # --- Supporting Frame (Side Plates) ---
                    # Connect axle tips to carriage
                    frame_target_x = -carr_y_pos
                    frame_len = abs(axle_x - frame_target_x)
                    frame_center_x = (axle_x + frame_target_x) / 2.0
                    
                    frame_thick = wheel_rad * 0.2
                    # Place support at the very tip of the axle
                    support_y = y_sign * (axle_len / 2.0 + frame_thick/2.0)

                    mat_frame = mathutils.Matrix.Translation((frame_center_x, support_y, axle_z))
                    bmesh.ops.create_cube(bm, size=1.0, matrix=mat_frame @ mathutils.Matrix.Scale(frame_len, 4, (1,0,0)) @ mathutils.Matrix.Scale(frame_thick, 4, (0,1,0)) @ mathutils.Matrix.Scale(frame_thick, 4, (0,0,1)))

    elif props.type_basic_joint == 'JOINT_SPHERICAL':
        # Ball and Socket Style
        
        # 1. Ball (Rotor) -> bm
        bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=radius)
        
        # 2. Stem (Attachment for Ball) -> bm
        stem_len = pin_len
        stem_r = pin_rad
        mat_stem = mathutils.Matrix.Translation((0, 0, radius + stem_len/2))
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=stem_r, radius2=stem_r, depth=stem_len, segments=16, matrix=mat_stem)
        
        # 3. Socket Housing (Stator) -> bm_stator
        # AI Editor Note: The stator is a simple base for the socket. A more complex
        # socket can be modeled manually and parented to the base bone.
        socket_r = radius + sub_thick
        housing_size = sub_size

        # Base Cylinder
        base_h = radius
        mat_base = mathutils.Matrix.Translation((0, 0, -radius))
        bmesh.ops.create_cone(bm_stator, cap_ends=True, radius1=socket_r, radius2=socket_r, depth=base_h, segments=32, matrix=mat_base)
        
        # Mounting Plate
        plate_w = housing_size * 2
        mat_plate = mathutils.Matrix.Translation((0, 0, -radius - base_h/2))
        # AI Editor Note: Fixed NameError by using 'sub_thick' instead of undefined 'bracket_thick'.
        bmesh.ops.create_cube(bm_stator, size=1.0, matrix=mat_plate @ mathutils.Matrix.Scale(plate_w, 4, (1,0,0)) @ mathutils.Matrix.Scale(plate_w, 4, (0,1,0)) @ mathutils.Matrix.Scale(sub_thick, 4, (0,0,1)))

    # --- Finalize Stator Mesh ---
    if stator_obj:
        # --- AI Editor Note: Safe BMesh Finalization ---
        # Only write to the mesh if the bmesh contains geometry. This prevents
        # errors if a generation step fails and leaves bm_stator empty.
        if bm_stator.verts:
            # Apply Auto Smooth to Stator
            apply_auto_smooth(stator_obj)
            
            # Write BMesh to Stator Object
            bmesh.ops.remove_doubles(bm_stator, verts=bm_stator.verts, dist=0.0001)
            bmesh.ops.recalc_face_normals(bm_stator, faces=bm_stator.faces)
            stator_obj.data.clear_geometry()
            bm_stator.to_mesh(stator_obj.data)
        
        bm_stator.free()

    # --- Finalize Pin Mesh ---
    if pin_obj:
        if bm_pin.verts:
            apply_auto_smooth(pin_obj)
            bmesh.ops.remove_doubles(bm_pin, verts=bm_pin.verts, dist=0.0001)
            bmesh.ops.recalc_face_normals(bm_pin, faces=bm_pin.faces)
            pin_obj.data.clear_geometry()
            bm_pin.to_mesh(pin_obj.data)
        bm_pin.free()

def generate_basic_shape_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates procedural geometry for basic primitive shapes using literal properties."""
    unit_scale = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    if props.type_basic_shape == 'SHAPE_PLANE':
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=(props.shape_size * s) / 2.0)

    elif props.type_basic_shape == 'SHAPE_CUBE':
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, verts=bm.verts, vec=(props.shape_length_x * s, props.shape_width_y * s, props.shape_height_z * s))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, (props.shape_height_z * s) / 2.0))

    elif props.type_basic_shape == 'SHAPE_CIRCLE':
        bmesh.ops.create_circle(bm, cap_ends=False, radius=props.shape_radius * s, segments=props.shape_vertices)

    elif props.type_basic_shape == 'SHAPE_UVSPHERE':
        bmesh.ops.create_uvsphere(bm, u_segments=props.shape_segments, v_segments=max(2, props.shape_segments//2), radius=props.shape_radius * s)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, props.shape_radius * s))

    elif props.type_basic_shape == 'SHAPE_ICOSPHERE':
        subdiv = min(max(1, props.shape_subdivisions), 6)
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=props.shape_radius * s)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, props.shape_radius * s))

    elif props.type_basic_shape == 'SHAPE_CYLINDER':
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=props.shape_radius * s, radius2=props.shape_radius * s, depth=props.shape_height * s, segments=props.shape_segments)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, (props.shape_height * s) / 2))

    elif props.type_basic_shape == 'SHAPE_CONE':
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=props.shape_radius * s, radius2=0, depth=props.shape_height * s, segments=props.shape_segments)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, (props.shape_height * s) / 2))

    elif props.type_basic_shape == 'SHAPE_TORUS':
        major_r = props.shape_major_radius * s
        minor_r = props.shape_tube_radius * s
        major_segs = props.shape_horizontal_segments
        minor_segs = props.shape_vertical_segments
        
        # Create profile circle in XZ plane at X=major_r
        mat = mathutils.Matrix.Translation((major_r, 0, 0)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
        ret = bmesh.ops.create_circle(bm, radius=minor_r, segments=minor_segs, matrix=mat)
        
        # Spin around Z axis
        edges = [e for e in ret.get('edges', []) if isinstance(e, bmesh.types.BMEdge)]
        if not edges: edges = list(bm.edges)
        bmesh.ops.spin(bm, geom=edges, cent=(0,0,0), axis=(0,0,1), angle=math.pi*2, steps=major_segs, use_duplicate=False)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, minor_r))


def generate_architectural_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates procedural architectural geometry into the provided BMesh."""
    bm.clear()
    u = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0
    
    t = props.type_architectural
    if t == 'WALL':
        length = props.length * s
        height = props.height * s
        thick = props.wall_thickness * s
        # Pivot at center-bottom
        mat = mathutils.Matrix.Translation((0, 0, height/2)) @ mathutils.Matrix.Diagonal((length, thick, height, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
        
    elif t == 'WINDOW':
        w = props.length * s
        h = props.height * s
        f_th = props.window_frame_thickness * s
        g_th = props.glass_thickness * s
        
        # Frame (4 parts)
        # Bottom/Top
        for z in [f_th/2, h - f_th/2]:
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, z)) @ mathutils.Matrix.Diagonal((w, f_th, f_th, 1.0)))
        # Left/Right
        for x in [-w/2 + f_th/2, w/2 - f_th/2]:
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((x, 0, h/2)) @ mathutils.Matrix.Diagonal((f_th, f_th, h - 2*f_th, 1.0)))
        # Glass
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Diagonal((w - 2*f_th, g_th, h - 2*f_th, 1.0)))

    elif t == 'DOOR':
        w = props.length * s
        h = props.height * s
        f_th = props.window_frame_thickness * s # Reuse for door frame
        # Just a flat slab with a frame
        # Frame
        for x in [-w/2 + f_th/2, w/2 - f_th/2]:
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((x, 0, h/2)) @ mathutils.Matrix.Diagonal((f_th, f_th*1.5, h, 1.0)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h - f_th/2)) @ mathutils.Matrix.Diagonal((w, f_th*1.5, f_th, 1.0)))
        # Slab
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Diagonal((w - 2.1*f_th, f_th*0.8, h - 1.1*f_th, 1.0)))

    elif t == 'COLUMN':
        r = props.radius * s
        h = props.height * s
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=r, radius2=r, depth=h, segments=32, matrix=mathutils.Matrix.Translation((0, 0, h/2)) @ mathutils.Matrix.Rotation(math.radians(0), 4, 'X'))
        # Rotate back to Z upright
        for v in bm.verts:
            v.co = mathutils.Matrix.Rotation(math.radians(90), 3, 'X') @ v.co

    elif t == 'BEAM':
        l = props.length * s
        w = props.width * s
        h = props.height * s
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((l/2, 0, 0)) @ mathutils.Matrix.Diagonal((l, w, h, 1.0)))

    elif t == 'STAIRS':
        count = props.step_count
        sh = props.step_height * s
        sd = props.step_depth * s
        sw = props.length * s
        for i in range(count):
            mat = mathutils.Matrix.Translation((0, i * sd + sd/2, i * sh + sh/2)) @ mathutils.Matrix.Diagonal((sw, sd, sh, 1.0))
            bmesh.ops.create_cube(bm, size=1.0, matrix=mat)

def generate_vehicle_mesh(bm: bmesh.types.BMesh, props: 'URDF_MechProps', obj: bpy.types.Object) -> None:
    """Generates procedural vehicle geometry into the provided BMesh."""
    bm.clear()
    u = bpy.context.scene.unit_settings.scale_length
    s = 1.0 / u if u > 0 else 1.0
    
    t = props.type_vehicle
    l = props.vehicle_length * s
    w = props.vehicle_width * s
    h = props.vehicle_height * s
    wr = props.vehicle_wheel_radius * s
    ww = props.vehicle_wheel_width * s
    wb = props.vehicle_wheelbase * s
    tw = props.vehicle_track_width * s
    
    if t == 'DRONE':
        # Hub
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0,0,h/2)) @ mathutils.Matrix.Diagonal((l*0.3, w*0.3, h, 1.0)))
        # Arms (4)
        arm_rad = h * 0.2
        for angle in [45, 135, 225, 315]:
            rad_angle = math.radians(angle)
            # Offset arm from center
            arm_mat = mathutils.Matrix.Rotation(rad_angle, 4, 'Z') @ mathutils.Matrix.Translation((l*0.4, 0, h/2)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=arm_rad, radius2=arm_rad, depth=l*0.8, segments=12, matrix=arm_mat)
            # Motor/Rotor at end
            rx = math.cos(rad_angle) * l * 0.8; ry = math.sin(rad_angle) * w * 0.8
            rotor_pos = mathutils.Vector((rx, ry, h))
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=wr, radius2=wr, depth=h*0.5, segments=16, matrix=mathutils.Matrix.Translation(rotor_pos))
        return

    # Basic Body for others
    body_h = h - wr # Leave room for wheels
    if t == 'TANK':
        # Low, wide body
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0,0,h/2)) @ mathutils.Matrix.Diagonal((l, w, h*0.6, 1.0)))
        # Turret
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((l*0.1, 0, h*0.8)) @ mathutils.Matrix.Diagonal((l*0.4, w*0.6, h*0.4, 1.0)))
        # Barrel
        bmesh.ops.create_cone(bm, cap_ends=True, radius1=h*0.05, radius2=h*0.03, depth=l*0.6, segments=16, matrix=mathutils.Matrix.Translation((l*0.6, 0, h*0.8)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))
    else:
        # Standard blocky body
        bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0,0,wr + body_h/2)) @ mathutils.Matrix.Diagonal((l, w, body_h, 1.0)))
        if t == 'CAR':
            # Cab/Roof
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((-l*0.1, 0, wr + body_h + body_h*0.3)) @ mathutils.Matrix.Diagonal((l*0.5, w*0.8, body_h*0.6, 1.0)))
        elif t == 'TRUCK':
             # Cab
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((l*0.35, 0, wr + body_h + body_h*0.3)) @ mathutils.Matrix.Diagonal((l*0.3, w, body_h*0.6, 1.0)))
            # Bed/Box
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((-l*0.15, 0, wr + body_h + body_h*0.6)) @ mathutils.Matrix.Diagonal((l*0.7, w, body_h*1.2, 1.0)))

    # Wheels (Standard 4-wheel layout for non-drone/tank)
    if t != 'TANK':
        for x in [wb/2, -wb/2]:
            for y in [tw/2, -tw/2]:
                wheel_mat = mathutils.Matrix.Translation((x, y, wr)) @ mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
                bmesh.ops.create_cone(bm, cap_ends=True, radius1=wr, radius2=wr, depth=ww, segments=24, matrix=wheel_mat)
    else:
        # Tank Tracks logic (simplified as side blocks)
        for y in [w/2 - ww/2, -w/2 + ww/2]:
            bmesh.ops.create_cube(bm, size=1.0, matrix=mathutils.Matrix.Translation((0, y, wr)) @ mathutils.Matrix.Diagonal((l*1.1, ww, wr*2, 1.0)))

def regenerate_mech_mesh(obj: bpy.types.Object, context: bpy.types.Context, mech_props: Optional['URDF_MechProps'] = None) -> None:
    """
    The central function for generating and updating the mesh of a parametric part.

    This function reads the `URDF_MechProps` from the object, dispatches to the
    appropriate mesh generation logic based on the part's category, and handles
    the setup of any associated modifiers (like the bore hole). It operates on a
    bmesh level for efficiency and precision.

    Args:
        obj: The mesh object whose geometry needs to be regenerated.
        context: The current Blender context.
        mech_props: Optional properties to use instead of the object's own properties.
    """
    props = None
    if mech_props:
        props = mech_props
    elif obj and hasattr(obj, "urdf_mech_props") and obj.urdf_mech_props.is_part:
        props = obj.urdf_mech_props

    if not props:
        return

    target_obj = obj
    is_rack = False

    # --- 1. Dispatch to correct generation logic based on category ---
    if props.category == 'SPRING':
        # Springs are handled entirely by their own Geometry Nodes setup.
        # The `wrapper_regenerate` function updates the custom properties that
        # drive the GN modifier, so no mesh regeneration is needed here.
        return
    elif props.category == 'CHAIN':
        # For chains, the `obj` is the main curve. We need to regenerate the
        # mesh of the hidden, instanced link object.
        target_obj = props.instanced_link_obj
        if not target_obj:
            return # No link object to regenerate.
    
    # --- 2. Perform BMesh operations ---
    mesh = target_obj.data
    bm = bmesh.new()

    if props.category == 'GEAR':
        generate_gear_mesh(bm, props, target_obj)
    elif props.category == 'RACK':
        generate_rack_mesh(bm, props, target_obj)
        is_rack = True
    elif props.category == 'FASTENER':
        generate_fastener_mesh(bm, props, target_obj, context)
    elif props.category == 'CHAIN':
        generate_chain_link_mesh(bm, props)
    elif props.category == 'ELECTRONICS':
        generate_electronics_mesh(bm, props, target_obj)
    elif props.category == 'WHEEL':
        generate_wheel_mesh(bm, props, target_obj)
    elif props.category == 'PULLEY':
        generate_pulley_mesh(bm, props, target_obj)
    elif props.category == 'BASIC_JOINT':
        generate_basic_joint_mesh(bm, props, target_obj, context)
    elif props.category == 'BASIC_SHAPE':
        generate_basic_shape_mesh(bm, props, target_obj)
    elif props.category == 'ARCHITECTURAL':
        generate_architectural_mesh(bm, props, target_obj)
    elif props.category == 'VEHICLE':
        generate_vehicle_mesh(bm, props, target_obj)
    elif props.category == 'ROPE':
        generate_rope_mesh(bm, props)

    # --- 3. Finalize Mesh and Modifiers ---
    if bm.verts: # Only update mesh if bmesh operations were performed
        # AI Editor Note: Add a weld/merge step to clean up the generated geometry.
        # This removes duplicate vertices created during procedural modeling (e.g., at
        # the seam of a cylinder or where tapered tooth faces meet) and is crucial
        # for making subsequent operations like Boolean modifiers stable and reliable.
        # This directly addresses the "unstable" or "half-hole" bore issue.
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_THRESHOLD)

        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        mesh.clear_geometry()
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
    else:
        bm.free()

    # --- 4. Handle Bore Modifier (for non-rack, non-internal gears) ---
    mod = target_obj.modifiers.get(f"{MOD_PREFIX}Bore")
    cutter = bpy.data.objects.get(f"{CUTTER_PREFIX}{target_obj.name}")
    
    use_bore = (
        props.category == 'GEAR' and
        props.type_gear != 'INTERNAL' and 
        not is_rack and
        props.gear_bore_radius > 0 and
        props.gear_bore_radius < props.gear_radius
    )

    if use_bore:
        if not cutter:
            cutter_mesh = bpy.data.meshes.new(f"{CUTTER_PREFIX}{target_obj.name}")
            cutter = bpy.data.objects.new(f"{CUTTER_PREFIX}{target_obj.name}", cutter_mesh)
            context.collection.objects.link(cutter)
        
        # --- AI Editor Note: Enforce Cutter Alignment & State ---
        # We enforce parenting and reset the transform every time to guarantee the cutter
        # is perfectly aligned with the gear. This prevents "half-hole" artifacts if the
        # cutter was moved or unparented.
        if cutter.parent != target_obj:
            cutter.parent = target_obj
            
        cutter.hide_set(True)
        cutter.hide_render = True
        cutter.display_type = 'WIRE'
        
        # Reset transform to local identity (aligned with parent)
        cutter.matrix_local = mathutils.Matrix.Identity(4)

        # --- AI Editor Note: Critical Fix for Bore Hole Artifacts ---
        # We must clear the existing geometry of the cutter mesh before adding the new one.
        # Without this, every parameter update appends a new cylinder to the mesh, causing
        # overlapping geometry (z-fighting) which confuses the Boolean modifier and results
        # in "half holes" or closed meshes.
        cutter.data.clear_geometry()

        # --- AI Editor Note: Unit-Aware Bore Hole ---
        unit_scale = context.scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0

        cutter_bm = bmesh.new()
        bore_segs = 32 if props.bore_type == 'ROUND' else 6
        bmesh.ops.create_cone(cutter_bm, cap_ends=True, radius1=props.gear_bore_radius * s, radius2=props.gear_bore_radius * s, depth=props.gear_width * 4.0 * s, segments=bore_segs)
        
        # AI Editor Note: Recalculate normals for the cutter to ensure stable boolean.
        bmesh.ops.recalc_face_normals(cutter_bm, faces=cutter_bm.faces)

        cutter_bm.to_mesh(cutter.data)
        cutter_bm.free()
        cutter.data.update()
        
        # --- AI Editor Note: Ensure Cutter is Smooth ---
        # The Boolean modifier inherits shading from the cutter operand.
        # We must set the cutter's faces to smooth so the bore hole is smooth
        # before the Auto Smooth (Edge Split) modifier processes it.
        for p in cutter.data.polygons:
            p.use_smooth = True
        
        if not mod:
            mod = target_obj.modifiers.new(name=f"{MOD_PREFIX}Bore", type='BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = cutter
    elif mod or cutter:
        if mod: target_obj.modifiers.remove(mod)
        if cutter: bpy.data.objects.remove(cutter, do_unlink=True)

    # AI Editor Note: Do not apply auto smooth for basic shapes.
    if props.category != 'BASIC_SHAPE':
        apply_auto_smooth(target_obj, is_rack=is_rack)

def wrapper_regenerate(self: 'URDF_MechProps', context: bpy.types.Context) -> None:
    """
    This function is the 'update' callback for all parametric properties in the
    `URDF_MechProps` group.

    It acts as a lean dispatcher. For most parts, it calls the main
    `regenerate_mech_mesh` function. For special cases like Springs and Chains,
    it updates the native custom properties that drive their Geometry Nodes setups.

    Args:
        self: The `URDF_MechProps` property group instance that was changed.
        context: The current Blender context.
    """
    # `self.id_data` is the object the property group is attached to.
    owner_obj = self.id_data 
    if not owner_obj or not self.is_part:
        return

    # --- Handle special cases that drive GN modifiers via custom properties ---
    if self.category == 'SPRING':
        u = context.scene.unit_settings.scale_length
        s = 1.0 / u if u > 0 else 1.0

        # For native springs/dampers, we don't regenerate a mesh. Instead, we update
        # the custom properties on the object that are used by the drivers
        # connected to the Geometry Nodes modifier.
        owner_obj["spring_teeth"] = self.spring_turns
        owner_obj["spring_radius"] = self.spring_radius * s
        owner_obj["spring_wire_thickness"] = self.spring_wire_thickness * s
        owner_obj["damper_housing_radius"] = self.outer_radius * s
        owner_obj["damper_rod_radius"] = self.bore_radius * s
        owner_obj["damper_piston_length"] = self.damper_piston_length * s
        owner_obj["damper_seat_radius"] = self.damper_seat_radius * s
        owner_obj["damper_seat_thickness"] = self.damper_seat_thickness * s

        # AI Editor Note: Handle switching between types.
        mod_spring = owner_obj.modifiers.get(NATIVE_SPRING_MOD_NAME)
        mod_damper = owner_obj.modifiers.get(NATIVE_DAMPER_MOD_NAME)
        mod_slinky = owner_obj.modifiers.get(NATIVE_SLINKY_MOD_NAME)

        from .core import setup_native_spring, setup_native_damper, setup_native_slinky

        if self.type_spring == 'SPRING' and not mod_spring:
            if mod_damper: owner_obj.modifiers.remove(mod_damper)
            if mod_slinky: owner_obj.modifiers.remove(mod_slinky)
            setup_native_spring(owner_obj, self.spring_start_obj, self.spring_end_obj)
        elif self.type_spring == 'DAMPER' and not mod_damper:
            if mod_spring: owner_obj.modifiers.remove(mod_spring)
            if mod_slinky: owner_obj.modifiers.remove(mod_slinky)
            setup_native_damper(owner_obj, self.spring_start_obj, self.spring_end_obj)
        elif self.type_spring == 'SPRING_SLINKY' and not mod_slinky:
            if mod_spring: owner_obj.modifiers.remove(mod_spring)
            if mod_damper: owner_obj.modifiers.remove(mod_damper)
            setup_native_slinky(owner_obj, self.spring_start_obj, self.spring_end_obj)
        
        # This category is handled entirely by Geometry Nodes, so we skip the BMesh regeneration.
        return

    elif self.category == 'ROPE':
        # Update native properties for the rope GN modifier
        owner_obj["rope_radius"] = self.rope_radius
        owner_obj["rope_strands"] = self.rope_strands
        owner_obj["rope_twist"] = self.twist
        owner_obj["rope_tube_mode"] = (self.type_rope == 'ROPE_TUBE')
        owner_obj["rope_is_synthetic"] = (self.type_rope == 'ROPE_SYNTHETIC')
        # Do not return early; we need to call regenerate_mech_mesh to update the line geometry.
        pass

    elif self.category == 'CHAIN':
        u = context.scene.unit_settings.scale_length
        s = 1.0 / u if u > 0 else 1.0
        # For chains, the UI properties update native Blender custom properties on the curve.
        # The Geometry Nodes drivers read from these native properties, ensuring the
        # setup continues to function even if the addon is removed.
        owner_obj["urdf_native_chain_pitch"] = self.length * s
        owner_obj["urdf_native_chain_res"] = self.chain_curve_res
        # The animation offset is handled by its own driver, not here.

    # --- For all parts with a BMesh-generated component, trigger regeneration ---
    # This includes Gears, Fasteners, and the link object of a Chain.
    regenerate_mech_mesh(owner_obj, context)

    # --- AI Editor Note: Sync Parametric Radius to Bone ---
    # If this part is parented to a bone (e.g. a generated joint), update the bone's
    # joint_radius to match. This keeps the gizmo in sync with the mesh.
    if owner_obj.parent and owner_obj.parent_type == 'BONE' and owner_obj.parent.type == 'ARMATURE':
        rig = owner_obj.parent
        pbone = rig.pose.bones.get(owner_obj.parent_bone)
        if pbone:
            # Sync the correct radius to the joint bone based on part category
            # Use unit scale to convert meters to BU for visual parity
            r = self.radius
            if self.category == 'GEAR': r = self.gear_radius
            elif self.category == 'WHEEL': r = self.wheel_radius
            elif self.category == 'PULLEY': r = self.pulley_radius
            elif self.category == 'BASIC_JOINT': r = self.joint_radius
            
            u = context.scene.unit_settings.scale_length
            s = 1.0 / u if u > 0 else 1.0
            
            u = context.scene.unit_settings.scale_length
            s = 1.0 / u if u > 0 else 1.0
            pbone.urdf_props.joint_radius = r * s
            
            # --- AI Editor Note: Immediate Gizmo Refresh ---
            # Explicitly trigger the gizmo update handler from core.
            # This ensures the visual cage stays in sync with real-time morphs.
            if hasattr(core, 'update_single_bone_gizmo'):
                core.update_single_bone_gizmo(pbone, context.scene.urdf_viz_gizmos)


def update_radius_prop(self: 'URDF_MechProps', context: bpy.types.Context) -> None:
    """
    Special update handler for the radius property.
    This ensures that when a category-specific radius is changed, we update the
    internal 'last_radius' for any proportional scaling logic (if still present).
    """
    r = self.radius
    if self.category == 'GEAR': r = self.gear_radius
    elif self.category == 'WHEEL': r = self.wheel_radius
    elif self.category == 'PULLEY': r = self.pulley_radius
    elif self.category == 'BASIC_JOINT': r = self.joint_radius
    
    self.last_radius = r
    wrapper_regenerate(self, context)

def get_mat_uniform_scale(self):
    if not self.use_nodes or not self.node_tree: return 1.0
    mapping = next((n for n in self.node_tree.nodes if n.type == 'MAPPING'), None)
    if mapping:
        return mapping.inputs['Scale'].default_value[0]
    return 1.0



def update_text_color(self, context):
    """Updates the dimension material color."""
    if isinstance(self, bpy.types.Scene):
        return
    
    obj = self
    if obj.get("urdf_is_dimension"):
        from . import operators
        operators.get_or_create_text_material(obj)
        obj.update_tag()

def set_mat_uniform_scale(self, value):
    if not self.use_nodes or not self.node_tree: return
    mapping = next((n for n in self.node_tree.nodes if n.type == 'MAPPING'), None)
    if mapping:
        mapping.inputs['Scale'].default_value = (value, value, value)

class URDF_TransmissionProperties(bpy.types.PropertyGroup):
    """Properties for defining a URDF transmission element."""
    type: bpy.props.StringProperty(name="Type", default="transmission_interface/SimpleTransmission", description="The type of the transmission")
    joint: bpy.props.StringProperty(name="Joint", description="The name of the joint to which the transmission is connected")
    hardware_interface: bpy.props.StringProperty(name="Hardware Interface", default="hardware_interface/EffortJointInterface", description="The hardware interface for the transmission")
    mechanical_reduction: bpy.props.FloatProperty(name="Mechanical Reduction", default=1.0, description="The mechanical reduction of the transmission")

class URDF_MaterialProperties(bpy.types.PropertyGroup):
    """Properties for defining a URDF material."""
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.8, 0.8, 0.8, 1.0),
        size=4,
        min=0.0,
        max=1.0,
        description="Color of the material",
        update=core.update_viewport_material
    )
    texture: bpy.props.PointerProperty(
        name="Texture",
        type=bpy.types.Image,
        description="Texture of the material"
    )

class URDF_CollisionProperties(bpy.types.PropertyGroup):
    """Properties for defining a URDF collision element."""
    shape: bpy.props.EnumProperty(
        name="Shape",
        items=[
            ('BOX', "Box", "A box shape"),
            ('CYLINDER', "Cylinder", "A cylinder shape"),
            ('SPHERE', "Sphere", "A sphere shape"),
            ('MESH', "Mesh", "A mesh shape"),
        ],
        default='MESH',
        description="The shape of the collision geometry"
    )
    collision_object: bpy.props.PointerProperty(
        name="Collision Object",
        type=bpy.types.Object,
        description="Use a separate object for collision geometry. If not set, the object itself will be used"
    )

class URDF_InertialProperties(bpy.types.PropertyGroup):
    """Properties for defining a URDF inertial element."""
    mass: bpy.props.FloatProperty(name="Mass", default=1.0, min=0.0, description="The mass of the link in kilograms")
    center_of_mass: bpy.props.FloatVectorProperty(name="Center of Mass", subtype='TRANSLATION', unit='LENGTH', size=3, description="The location of the center of mass relative to the link's origin")
    ixx: bpy.props.FloatProperty(name="Ixx", default=1.0, description="The xx component of the inertia tensor")
    iyy: bpy.props.FloatProperty(name="Iyy", default=1.0, description="The yy component of the inertia tensor")
    izz: bpy.props.FloatProperty(name="Izz", default=1.0, description="The zz component of the inertia tensor")
    ixy: bpy.props.FloatProperty(name="Ixy", default=0.0, description="The xy component of the inertia tensor")
    ixz: bpy.props.FloatProperty(name="Ixz", default=0.0, description="The xz component of the inertia tensor")
    iyz: bpy.props.FloatProperty(name="Iyz", default=0.0, description="The yz component of the inertia tensor")

class URDF_WrapItem(bpy.types.PropertyGroup):
    """A helper property group for managing wrap objects in the UI list."""
    target: bpy.props.PointerProperty(type=bpy.types.Object, name="Wrap Object", description="An object that the chain wraps around")

class URDF_MechProps(bpy.types.PropertyGroup):
    """
    A PropertyGroup to store all parameters for a procedurally generated
    mechanical part. This is attached to the part object itself.
    """
    is_part: bpy.props.BoolProperty(default=False, description="Whether this object is a parametric part created by the addon")
    category: bpy.props.EnumProperty(name="Category", items=ALL_CATEGORIES_SORTED, update=wrapper_regenerate, description="The main category of the parametric part")
    type_gear: bpy.props.EnumProperty(name="Type", items=GEAR_TYPES, update=wrapper_regenerate, description="The specific type of gear to generate")
    type_rack: bpy.props.EnumProperty(name="Type", items=RACK_TYPES, update=wrapper_regenerate, description="The specific type of rack to generate")
    type_basic_shape: bpy.props.EnumProperty(name="Type", items=BASIC_SHAPE_TYPES, update=wrapper_regenerate, description="The specific type of basic shape to generate")
    type_pulley: bpy.props.EnumProperty(name="Type", items=PULLEY_TYPES, update=wrapper_regenerate, description="The specific type of pulley to generate")
    type_rope: bpy.props.EnumProperty(name="Type", items=ROPE_TYPES, update=wrapper_regenerate, description="The specific type of rope to generate")
    type_spring: bpy.props.EnumProperty(name="Type", items=SPRING_TYPES, update=wrapper_regenerate, description="The specific type of spring to generate")
    type_fastener: bpy.props.EnumProperty(name="Type", items=FASTENER_TYPES, update=wrapper_regenerate, description="The specific type of fastener to generate")
    type_chain: bpy.props.EnumProperty(name="Type", items=CHAIN_TYPES, update=wrapper_regenerate, description="The specific type of chain or belt to generate")
    type_wheel: bpy.props.EnumProperty(name="Type", items=WHEEL_TYPES, update=wrapper_regenerate, description="The specific type of wheel to generate")
    type_basic_joint: bpy.props.EnumProperty(name="Type", items=BASIC_JOINT_TYPES, update=wrapper_regenerate, description="The specific type of basic joint to generate")
    type_electronics: bpy.props.EnumProperty(name="Type", items=ALL_ELECTRONICS_TYPES, update=wrapper_regenerate, description="The specific type of electronic component")
    type_architectural: bpy.props.EnumProperty(name="Type", items=ARCHITECTURAL_TYPES, update=wrapper_regenerate, description="The specific type of architectural element to generate")
    type_vehicle: bpy.props.EnumProperty(name="Type", items=VEHICLE_TYPES, update=wrapper_regenerate, description="The specific type of vehicle to generate")
    
    # --- GEOMETRY PROPERTIES (Literal Naming) ---
    # These properties match the GUI labels and are specific to each mechanical category.

    # 1. GEARS
    gear_radius: bpy.props.FloatProperty(name="Gear Radius", default=0.05, min=0.001, unit='LENGTH', update=update_radius_prop)
    gear_width: bpy.props.FloatProperty(name="Gear Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    gear_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=24, min=3, update=wrapper_regenerate)
    gear_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.005, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    gear_tooth_taper: bpy.props.FloatProperty(name="Tooth Taper", default=0.8, min=0.0, max=1.5, update=wrapper_regenerate)
    gear_bore_radius: bpy.props.FloatProperty(name="Bore Radius", default=0.0, min=0.0, unit='LENGTH', update=wrapper_regenerate)
    gear_outer_radius: bpy.props.FloatProperty(name="Outer Radius (Ring)", default=0.06, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    # 2. RACKS
    rack_width: bpy.props.FloatProperty(name="Rack Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rack_height: bpy.props.FloatProperty(name="Rack Height", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rack_length: bpy.props.FloatProperty(name="Rack Length", default=0.2, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rack_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=40, min=1, update=wrapper_regenerate)
    rack_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.005, min=0.0001, unit='LENGTH', update=wrapper_regenerate)

    # 3. FASTENERS (Realistic Defaults for M8)
    fastener_radius: bpy.props.FloatProperty(name="Fastener Radius", default=0.004, min=0.0005, unit='LENGTH', update=wrapper_regenerate)
    fastener_length: bpy.props.FloatProperty(name="Fastener Length", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    # 4. SPRINGS
    spring_radius: bpy.props.FloatProperty(name="Spring Radius", default=0.015, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    spring_wire_thickness: bpy.props.FloatProperty(name="Wire Thickness", default=0.002, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    spring_turns: bpy.props.IntProperty(name="Turns", default=10, min=1, update=wrapper_regenerate)
    
    # 5. CHAINS & BELTS (Realistic Defaults for 1/2 inch pitch)
    chain_pitch: bpy.props.FloatProperty(name="Chain Pitch", default=0.0127, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_roller_radius: bpy.props.FloatProperty(name="Roller Radius", default=0.004, min=0.0005, unit='LENGTH', update=wrapper_regenerate)
    chain_roller_length: bpy.props.FloatProperty(name="Roller Length", default=0.008, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_plate_height: bpy.props.FloatProperty(name="Plate Height", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_plate_thickness: bpy.props.FloatProperty(name="Plate Thickness", default=0.0015, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    belt_width: bpy.props.FloatProperty(name="Belt Width", default=0.015, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    belt_thickness: bpy.props.FloatProperty(name="Belt Thickness", default=0.002, min=0.0001, unit='LENGTH', update=wrapper_regenerate)

    # 6. WHEELS
    wheel_radius: bpy.props.FloatProperty(name="Wheel Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_width: bpy.props.FloatProperty(name="Wheel Width", default=0.04, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_hub_radius: bpy.props.FloatProperty(name="Hub Radius", default=0.012, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_hub_length: bpy.props.FloatProperty(name="Hub Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_tread_count: bpy.props.IntProperty(name="Tread Count", default=24, min=1, update=wrapper_regenerate)
    wheel_sub_radius: bpy.props.FloatProperty(name="Sub-Radius", default=0.008, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_sub_length: bpy.props.FloatProperty(name="Sub-Length", default=0.025, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_sub_arrays: bpy.props.IntProperty(name="Roller Arrays", default=1, min=1, update=wrapper_regenerate)
    wheel_sub_support_thickness: bpy.props.FloatProperty(name="Support Thickness", default=0.002, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    wheel_sub_support_length: bpy.props.FloatProperty(name="Support Length", default=0.005, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_axle_length: bpy.props.FloatProperty(name="Axle Length", default=0.045, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_thickness: bpy.props.FloatProperty(name="Carriage Thickness", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    # 7. PULLEYS
    pulley_radius: bpy.props.FloatProperty(name="Pulley Radius", default=0.03, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pulley_width: bpy.props.FloatProperty(name="Pulley Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pulley_groove_depth: bpy.props.FloatProperty(name="Groove Depth", default=0.005, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    pulley_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=20, min=3, update=wrapper_regenerate)

    # 8. ROPES & CABLES
    rope_radius: bpy.props.FloatProperty(name="Rope Radius", default=0.003, min=0.0005, unit='LENGTH', update=wrapper_regenerate)
    rope_length: bpy.props.FloatProperty(name="Rope Length", default=0.5, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rope_strands: bpy.props.IntProperty(name="Strands", default=7, min=1, update=wrapper_regenerate)

    # 9. BASIC JOINTS
    joint_width: bpy.props.FloatProperty(name="Joint Width", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_radius: bpy.props.FloatProperty(name="Joint Radius", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_pin_radius: bpy.props.FloatProperty(name="Pin Radius", default=0.005, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_pin_length: bpy.props.FloatProperty(name="Pin Length", default=0.06, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_sub_size: bpy.props.FloatProperty(name="Sub-Component Size", default=0.04, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_sub_thickness: bpy.props.FloatProperty(name="Sub-Component Thickness", default=0.005, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_frame_width: bpy.props.FloatProperty(name="Frame Width", default=0.04, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_frame_length: bpy.props.FloatProperty(name="Frame Length", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_carriage_width: bpy.props.FloatProperty(name="Carriage Width", default=0.08, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    joint_carriage_thickness: bpy.props.FloatProperty(name="Carriage Thickness", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rotor_arm_length: bpy.props.FloatProperty(name="Rotor Arm Length", default=0.15, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rotor_arm_width: bpy.props.FloatProperty(name="Rotor Arm Width", default=0.03, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rotor_arm_height: bpy.props.FloatProperty(name="Rotor Arm Height", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    # 10. ELECTRONICS (Realistic Hobby Scale)
    motor_radius: bpy.props.FloatProperty(name="Motor Radius", default=0.018, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    motor_length: bpy.props.FloatProperty(name="Motor Length", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    motor_height: bpy.props.FloatProperty(name="Motor Height", default=0.035, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    motor_shaft_radius: bpy.props.FloatProperty(name="Shaft Radius", default=0.003, min=0.0005, unit='LENGTH', update=wrapper_regenerate)
    motor_shaft_length: bpy.props.FloatProperty(name="Shaft Length", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    
    sensor_radius: bpy.props.FloatProperty(name="Sensor Radius", default=0.035, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    sensor_length: bpy.props.FloatProperty(name="Sensor Length", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    sensor_height: bpy.props.FloatProperty(name="Sensor Height", default=0.015, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    
    camera_case_length: bpy.props.FloatProperty(name="Case Length", default=0.03, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    camera_case_width: bpy.props.FloatProperty(name="Case Width", default=0.03, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    camera_case_height: bpy.props.FloatProperty(name="Case Height", default=0.03, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    camera_lens_radius: bpy.props.FloatProperty(name="Lens Radius", default=0.008, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    
    pcb_length: bpy.props.FloatProperty(name="PCB Length", default=0.08, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pcb_width: bpy.props.FloatProperty(name="PCB Width", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pcb_thickness: bpy.props.FloatProperty(name="PCB Thickness", default=0.002, min=0.0005, unit='LENGTH', update=wrapper_regenerate)
    pcb_hole_radius: bpy.props.FloatProperty(name="Hole Radius", default=0.002, min=0.0, unit='LENGTH', update=wrapper_regenerate)
    
    ic_length: bpy.props.FloatProperty(name="IC Length", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    ic_width: bpy.props.FloatProperty(name="IC Width", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    ic_height: bpy.props.FloatProperty(name="IC Height", default=0.005, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    ic_pin_count: bpy.props.IntProperty(name="Pin Count", default=8, min=2, step=2, update=wrapper_regenerate)

    # 11. ARCHITECTURAL
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.2, min=0.01, unit='LENGTH', update=wrapper_regenerate)
    window_frame_thickness: bpy.props.FloatProperty(name="Frame Thickness", default=0.05, min=0.005, unit='LENGTH', update=wrapper_regenerate)
    glass_thickness: bpy.props.FloatProperty(name="Glass Thickness", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    step_count: bpy.props.IntProperty(name="Step Count", default=10, min=1, update=wrapper_regenerate)
    step_height: bpy.props.FloatProperty(name="Step Height", default=0.18, min=0.01, unit='LENGTH', update=wrapper_regenerate)
    step_depth: bpy.props.FloatProperty(name="Step Depth", default=0.28, min=0.01, unit='LENGTH', update=wrapper_regenerate)

    # 12. VEHICLES
    vehicle_length: bpy.props.FloatProperty(name="Vehicle Length", default=4.5, min=0.1, unit='LENGTH', update=wrapper_regenerate)
    vehicle_width: bpy.props.FloatProperty(name="Vehicle Width", default=1.8, min=0.1, unit='LENGTH', update=wrapper_regenerate)
    vehicle_height: bpy.props.FloatProperty(name="Vehicle Height", default=1.4, min=0.1, unit='LENGTH', update=wrapper_regenerate)
    vehicle_wheel_radius: bpy.props.FloatProperty(name="Wheel Radius", default=0.3, min=0.01, unit='LENGTH', update=wrapper_regenerate)
    vehicle_wheel_width: bpy.props.FloatProperty(name="Wheel Width", default=0.2, min=0.01, unit='LENGTH', update=wrapper_regenerate)
    vehicle_wheelbase: bpy.props.FloatProperty(name="Wheelbase", default=2.7, min=0.1, unit='LENGTH', update=wrapper_regenerate)
    vehicle_track_width: bpy.props.FloatProperty(name="Track Width", default=1.5, min=0.1, unit='LENGTH', update=wrapper_regenerate)

    # 11. BASIC SHAPES
    shape_size: bpy.props.FloatProperty(name="Size", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_length_x: bpy.props.FloatProperty(name="Length (X)", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_width_y: bpy.props.FloatProperty(name="Width (Y)", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_height_z: bpy.props.FloatProperty(name="Height (Z)", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_radius: bpy.props.FloatProperty(name="Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_height: bpy.props.FloatProperty(name="Height", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_vertices: bpy.props.IntProperty(name="Vertices", default=32, min=3, update=wrapper_regenerate)
    shape_segments: bpy.props.IntProperty(name="Segments", default=32, min=3, update=wrapper_regenerate)
    shape_subdivisions: bpy.props.IntProperty(name="Subdivisions", default=2, min=1, update=wrapper_regenerate)
    shape_major_radius: bpy.props.FloatProperty(name="Major Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_tube_radius: bpy.props.FloatProperty(name="Tube Radius", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_horizontal_segments: bpy.props.IntProperty(name="Horizontal Segments", default=48, min=3, update=wrapper_regenerate)
    shape_vertical_segments: bpy.props.IntProperty(name="Vertical Segments", default=12, min=3, update=wrapper_regenerate)

    # --- SHARED / UTILITY PROPERTIES (Internal or Multi-purpose) ---
    bore_type: bpy.props.EnumProperty(name="Bore Type", items=[('ROUND', "Round", "A round hole"), ('HEX', "Hex", "A hexagonal hole")], update=wrapper_regenerate)
    twist: bpy.props.FloatProperty(name="Twist / Bevel Angle", default=math.radians(20.0), subtype='ANGLE', unit='ROTATION', update=wrapper_regenerate)
    tooth_spacing: bpy.props.FloatProperty(name="Teeth Spacing", default=0.5, min=0.01, max=0.99, update=wrapper_regenerate)
    wheel_tread_pattern: bpy.props.EnumProperty(name="Tread Pattern", items=WHEEL_TREAD_PATTERNS, default='BLOCKS', update=wrapper_regenerate)
    wheel_side_pattern: bpy.props.EnumProperty(name="Side Pattern", items=WHEEL_SIDE_PATTERNS, default='NONE', update=wrapper_regenerate)
    wheel_pattern_spacing: bpy.props.FloatProperty(name="Pattern Spacing", default=0.002, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    wheel_pattern_depth: bpy.props.FloatProperty(name="Pattern Depth", default=0.002, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    
    # Deprecated/Shared properties kept for backward compatibility or core logic (will be phased out in generation functions)
    radius: bpy.props.FloatProperty(name="Radius", default=0.05, min=0.001, unit='LENGTH', update=update_radius_prop)
    length: bpy.props.FloatProperty(name="Length", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    height: bpy.props.FloatProperty(name="Height", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.004, min=0.0001, unit='LENGTH', update=wrapper_regenerate)
    last_radius: bpy.props.FloatProperty(default=0.0, options={'HIDDEN'})

    # Pointers and collections (Must be kept at the end or in a separate block)
    
    
    # Pointers for spring helper objects
    spring_start_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="The Empty object controlling the start of the spring")
    spring_end_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="The Empty object controlling the end of the spring")
    rope_start_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="Start hook for the rope")
    rope_end_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="End hook for the rope")
    joint_stator_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="The static base object for a basic joint")
    joint_pin_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="The pin object for a revolute joint")
    joint_screw_obj: bpy.props.PointerProperty(type=bpy.types.Object, description="The screw object for a prismatic joint")
    instanced_link_obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Instanced Link Object", description="The hidden mesh object that is instanced along the chain's curve")
    
    chain_target: bpy.props.PointerProperty(type=bpy.types.Object, name="Target", description="The target object for the chain to follow")
    chain_wrap_items: bpy.props.CollectionProperty(type=URDF_WrapItem, description="A list of objects the chain wraps around")
    chain_wrap_collection: bpy.props.PointerProperty(type=bpy.types.Collection, name="Wrap Collection", description="The collection containing objects the chain wraps around")
    # NEW: Picker for easier UI selection of wrap targets
    wrap_picker: bpy.props.PointerProperty(type=bpy.types.Object, name="Pick Object", description="Select an object to add to the wrap bundle")
    chain_active_index: bpy.props.IntProperty(description="The index of the active hook in the UI list")
    
    chain_driver: bpy.props.PointerProperty(type=bpy.types.Object, name="Drive Source", description="The Empty object that rotationally drives the chain animation")
    chain_follower_proxy: bpy.props.PointerProperty(type=bpy.types.Object, name="Path Follower", description="The Empty object that follows the path and can be interactively controlled")
    chain_drive_target: bpy.props.PointerProperty(type=bpy.types.Object, name="Driver Object", description="The object (e.g., sprocket) that drives the chain movement")

    # Slinky specific hooks collection (uses the same item type as chain wrap)
    slinky_hooks: bpy.props.CollectionProperty(type=URDF_WrapItem, description="A list of middle hooks that guide the curved spring path")
    slinky_active_index: bpy.props.IntProperty(description="Active index for the slinky hooks UI list")
    slinky_picker: bpy.props.PointerProperty(type=bpy.types.Object, name="Pick Hook", description="Select an object to add as a middle guide hook for the slinky")

    # Chain Drive Settings
    chain_drive_radius: bpy.props.FloatProperty(name="Drive Radius", default=1.0, description="The effective radius of the driver object (calculated)", unit='LENGTH', update=core.update_chain_driver_settings)
    chain_drive_ratio: bpy.props.FloatProperty(name="Manual Ratio", default=1.0, description="Manual multiplier for the drive ratio", update=core.update_chain_driver_settings)
    chain_drive_invert: bpy.props.BoolProperty(name="Invert Drive", default=False, description="Invert the direction of the chain movement", update=core.update_chain_driver_settings)

    # Collision and Inertial Properties
    collision: bpy.props.PointerProperty(type=URDF_CollisionProperties)
    inertial: bpy.props.PointerProperty(type=URDF_InertialProperties)
    material: bpy.props.PointerProperty(type=URDF_MaterialProperties)

class URDF_MimicDriver(bpy.types.PropertyGroup):
    """A helper property group for managing mimic joint drivers in the UI list."""
    target_bone: bpy.props.StringProperty(name="Target", description="The name of the bone that drives this bone's motion")
    ratio: bpy.props.FloatProperty(name="Ratio", default=1.0, description="The multiplication factor for the mimic relationship")


class URDF_JointEditorSettings(bpy.types.PropertyGroup):
    """Scene-level properties for the global Joint Editor tool, allowing the UI to be decoupled from the active bone."""
    joint_type: bpy.props.EnumProperty(items=[('none', "None", "No joint, bone is a free-floating link"), ('base', "Base", "A root joint that can be moved and rotated freely"), ('fixed', "Fixed", "A rigid connection with no movement"), ('revolute', "Revolute", "A hinge-like joint that rotates around a single axis"), ('continuous', "Continuous", "A revolute joint with no limits"), ('prismatic', "Linear", "A sliding joint that moves along a single axis")], default='none', name="Type", description="The type of the URDF joint", update=core.urdf_joint_editor_update_callback)
    axis_enum: bpy.props.EnumProperty(items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], default='Z', name="Axis", description="The axis of rotation or translation for the joint", update=core.urdf_joint_editor_update_callback)
    
    joint_radius: bpy.props.FloatProperty(
        name="Joint Radius",
        description="Effective radius of the joint for ratio calculations",
        default=0.05,
        min=0.0,
        subtype='DISTANCE',
        unit='LENGTH',
        update=core.urdf_joint_editor_update_callback
    )
    gizmo_radius: bpy.props.FloatProperty(
        name="Gizmo Radius",
        description="Adjusts the visual radius of the gizmo in the viewport without affecting physics",
        default=0.1,
        min=0.0,
        subtype='DISTANCE',
        unit='LENGTH',
        update=core.urdf_joint_editor_update_callback
    )
    lower_limit: bpy.props.FloatProperty(name="Lower", default=-90.0, description="The lower limit of the joint's motion (in degrees for revolute, meters for prismatic)", update=core.urdf_joint_editor_update_callback)
    upper_limit: bpy.props.FloatProperty(name="Upper", default=90.0, description="The upper limit of the joint's motion (in degrees for revolute, meters for prismatic)", update=core.urdf_joint_editor_update_callback)
    ik_chain_length: bpy.props.IntProperty(name="IK Chain Length", default=0, min=0, max=255, description="The length of the IK chain, starting from this bone", update=core.urdf_joint_editor_update_callback)


class URDF_Properties(bpy.types.PropertyGroup):
    """
    A PropertyGroup to store all kinematic and physical parameters for a joint.
    This is attached to a PoseBone.
    """
    joint_type: bpy.props.EnumProperty(items=[('none', "None", "No joint, bone is a free-floating link"), ('base', "Base", "A root joint that can be moved and rotated freely"), ('fixed', "Fixed", "A rigid connection with no movement"), ('revolute', "Revolute", "A hinge-like joint that rotates around a single axis"), ('continuous', "Continuous", "A revolute joint with no limits"), ('prismatic', "Linear", "A sliding joint that moves along a single axis")], default='none', description="The type of the URDF joint", update=lambda s, c: urdf_prop_update(s, c, 'joint_type'))
    axis_enum: bpy.props.EnumProperty(items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], default='Z', update=lambda s, c: urdf_prop_update(s, c, 'axis_enum'), description="The axis of rotation or translation for the joint")
    
    joint_radius: bpy.props.FloatProperty(
        name="Joint Radius",
        description="Effective radius of the joint for ratio calculations. Auto-calculated from mesh on creation",
        default=0.05,
        min=0.0,
        subtype='DISTANCE',
        unit='LENGTH',
        update=lambda s, c: urdf_prop_update(s, c, 'joint_radius')
    )
    gizmo_radius: bpy.props.FloatProperty(
        name="Gizmo Radius",
        description="Adjusts the visual radius of the gizmo in the viewport without affecting physics",
        default=0.1,
        min=0.0,
        subtype='DISTANCE',
        unit='LENGTH',
        update=lambda s, c: urdf_prop_update(s, c, 'gizmo_radius')
    )
    lower_limit: bpy.props.FloatProperty(name="Lower", default=-90.0, update=lambda s, c: urdf_prop_update(s, c, 'lower_limit'), description="The lower limit of the joint's motion (in degrees for revolute, meters for prismatic)")
    upper_limit: bpy.props.FloatProperty(name="Upper", default=90.0, update=lambda s, c: urdf_prop_update(s, c, 'upper_limit'), description="The upper limit of the joint's motion (in degrees for revolute, meters for prismatic)")
    ratio_target_bone: bpy.props.StringProperty(name="Target Bone", description="The bone that will drive this bone's motion")
    ratio_ref_bone: bpy.props.StringProperty(name="Ref Bone", description="A reference bone for calculating the gear ratio")
    ratio_value: bpy.props.FloatProperty(name="Ratio", default=1.0, description="The multiplication factor for the gear/mimic relationship", update=lambda s, c: urdf_prop_update(s, c, 'ratio_value'))
    ratio_invert: bpy.props.BoolProperty(name="Invert", default=False, description="Invert the direction of the driven motion", update=lambda s, c: urdf_prop_update(s, c, 'ratio_invert'))
    mimic_drivers: bpy.props.CollectionProperty(type=URDF_MimicDriver, description="A list of mimic drivers for this joint")
    mimic_index: bpy.props.IntProperty(description="The index of the active mimic driver in the UI list")
    ik_chain_length: bpy.props.IntProperty(name="IK Chain Length", default=0, min=0, max=255, update=core.update_ik_chain_length, description="The length of the IK chain, starting from this bone")

    # Collision and Inertial Properties
    collision: bpy.props.PointerProperty(type=URDF_CollisionProperties)
    inertial: bpy.props.PointerProperty(type=URDF_InertialProperties)
    material: bpy.props.PointerProperty(type=URDF_MaterialProperties)
    transmission: bpy.props.PointerProperty(type=URDF_TransmissionProperties)

class URDF_AI_Properties(bpy.types.PropertyGroup):
    """
    Properties for the AI Robot Factory. This stores the user's prompt,
    API key, and other settings for the AI generation feature.
    
    AI Editor Note:
    This property group is the data model for the AI panel. When adding new
    UI controls to the AI panel (like model selection dropdowns, temperature
    sliders, etc.), their corresponding properties should be defined here first.
    The operator `URDF_OT_Execute_AI_Prompt` will then access these properties
    to configure its request to the AI service.
    """
    # AI Editor Note: The 'name' parameter is for the UI label, and the
    # 'description' is for the tooltip. These should be user-friendly.
    
    # --- AI Editor Note: New AI Source Selection ---
    # Allows the user to choose between free/local AI or a paid API service.
    ai_source: bpy.props.EnumProperty(
        name="AI Source",
        items=[
            ('FREE', "Free (Local/Built-in)", "Use built-in templates or local AI models"),
            ('API', "API Key (Cloud)", "Use an external AI service via API key")
        ],
        default='FREE',
        description="Select the AI backend to use for generation"
    )

    api_key: bpy.props.StringProperty(
        name="API Key",
        description="Your API key for the AI service. It is stored securely and not exported",
        subtype='PASSWORD'
    )
    
    api_prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Describe the robot you want to build. Be as descriptive as possible",
        default="Create a simple 4-wheeled rover with a robotic arm on top. The arm should have 3 joints.",
        subtype='NONE' # Use 'NONE' for a simple text field. For a larger box, the UI layout uses `layout.prop` with a specific `text` field.
    )
    
    robot_template: bpy.props.EnumProperty(
        name="Template",
        items=[
            ('ROVER', "Rover (6-Wheel + Arm)", "A 6-wheeled rover with a manipulator arm"),
            ('ARM', "Robotic Arm (6-DOF)", "A 6-degree-of-freedom robotic arm with alternating joints"),
            ('MOBILE_BASE', "Mobile Base (Diff Drive)", "A 2-wheeled differential drive base with caster"),
            ('QUADRUPED', "Quadruped Base", "A base body ready for quadruped leg attachment")
        ],
        description="Select a pre-defined robot template to generate"
    )

def _update_scene_lighting_wrap(self, context):
    from . import core
    if hasattr(core, 'update_scene_lighting'):
        core.update_scene_lighting(self, context)

def _update_selected_light_wrap(self, context):
    from . import core
    if hasattr(core, 'update_selected_light'):
        core.update_selected_light(self, context)

class URDF_LightingProperties(bpy.types.PropertyGroup):
    """
    Properties for the Lighting & Environment panel.
    Allows for quick toggling of lighting presets and background settings.
    """
    light_preset: bpy.props.EnumProperty(
        name="Environment Preset",
        items=[
            ('STUDIO', "Studio (3-Point)", "Clean studio lighting with soft shadows"),
            ('OUTDOOR', "Outdoor (Sun)", "Bright direct light with sharp shadows"),
            ('EMPTY', "Ambient Only", "Uniform lighting without direct sources")
        ],
        default='STUDIO',
        update=_update_scene_lighting_wrap
    )
    


    # --- Smart Light Editing (For Active Light) ---
    selected_light_type: bpy.props.EnumProperty(
        name="Light Type",
        items=[
            ('POINT', "Point", "Omni-directional point light"),
            ('SUN', "Sun", "Directional light from infinity"),
            ('SPOT', "Spot", "Directional cone light"),
            ('AREA', "Area", "Planar light source")
        ],
        default='POINT',
        update=_update_selected_light_wrap
    )
    
    selected_light_energy: bpy.props.FloatProperty(
        name="Local Power",
        min=0.0,
        default=10.0,
        update=_update_selected_light_wrap
    )

    selected_light_shading: bpy.props.EnumProperty(
        name="Shading Mode",
        items=[
            ('GRADIENT', "Realistic (Gradient)", "Smooth light falloff and reflections"),
            ('FLAT', "True Constant (Toon)", "Zero-gradient parallel rays and 100% sharp shadows")
        ],
        default='GRADIENT',
        update=_update_selected_light_wrap
    )

    selected_light_color: bpy.props.FloatVectorProperty(
        name="Light Color",
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        update=_update_selected_light_wrap
    )

    selected_light_target: bpy.props.PointerProperty(
        name="Track Target",
        type=bpy.types.Object,
        description="Object for the light to point towards (Eyedropper tool)"
    )
    
    base_color: bpy.props.FloatVectorProperty(
        name="Global Tint",
        description="Multiply all light colors by this color",
        subtype='COLOR',
        size=4,
        default=(1.0, 1.0, 1.0, 1.0),
        update=_update_scene_lighting_wrap
    )
    
    background_color: bpy.props.FloatVectorProperty(
        name="Background",
        description="Scene background color (World Color)",
        subtype='COLOR',
        size=4,
        default=(0.04, 0.04, 0.04, 1.0),
        update=_update_scene_lighting_wrap
    )
    
    light_intensity: bpy.props.FloatProperty(
        name="Intensity",
        description="Multiplier for all light strengths",
        default=1.0,
        min=0.0,
        max=10.0,
        update=_update_scene_lighting_wrap
    )
    
    use_shadows: bpy.props.BoolProperty(
        name="Cast Shadows",
        description="Enable or disable shadow calculation for all lights",
        default=True,
        update=core.update_scene_lighting
    )

# --- Asset Library Helpers ---
def get_asset_libraries_callback(self, context):
    """Callback to populate the asset library dropdown"""
    items = [('LOCAL', "Current File", "Assets in the current file", 'ASSET_MANAGER', 0)]
    try:
        libs = getattr(context.preferences.filepaths, "asset_libraries", [])
        for i, lib in enumerate(libs):
            if lib.name:
                items.append((lib.name, lib.name, str(lib.path), 'FILE_FOLDER', i + 1))
    except Exception as e:
        print(f"Error in get_asset_libraries_callback: {e}")
    return items

def get_asset_catalogs_callback(self, context):
    """Reads blender_assets.cats.txt from the selected library and returns catalog items."""
    items = [('NONE', "None selected", "", 'X', 0)]
    try:
        lib_name = self.target_library
        if lib_name and lib_name != 'LOCAL':
            libs = getattr(context.preferences.filepaths, "asset_libraries", [])
            lib_path = ""
            for lib in libs:
                if lib.name == lib_name:
                    lib_path = lib.path
                    break
            if lib_path:
                cat_file = os.path.join(lib_path, "blender_assets.cats.txt")
                if os.path.exists(cat_file):
                    with open(cat_file, "r", encoding='utf-8') as f:
                        for i, line in enumerate(f):
                            line = line.strip()
                            if not line or line.startswith(("#", "VERSION")):
                                continue
                            parts = line.split(":")
                            if len(parts) >= 3:
                                uid, path, name = parts[0], parts[1], parts[2]
                                items.append((uid, name, path, 'ASSET_MANAGER', i + 1))
    except Exception as e:
        print(f"Error in get_asset_catalogs_callback: {e}")
    return items

def get_asset_catalogs_for_library(lib_name, context):
    """Reads blender_assets.cats.txt for a given library name string. Used by import sub-panel."""
    items = [('NONE', "None selected", "", 'X', 0)]
    try:
        if lib_name and lib_name != 'LOCAL':
            libs = getattr(context.preferences.filepaths, "asset_libraries", [])
            lib_path = ""
            for lib in libs:
                if lib.name == lib_name:
                    lib_path = lib.path
                    break
            if lib_path:
                cat_file = os.path.join(lib_path, "blender_assets.cats.txt")
                if os.path.exists(cat_file):
                    with open(cat_file, "r", encoding='utf-8') as f:
                        for i, line in enumerate(f):
                            line = line.strip()
                            if not line or line.startswith(("#", "VERSION")):
                                continue
                            parts = line.split(":")
                            if len(parts) >= 3:
                                uid, path, name = parts[0], parts[1], parts[2]
                                items.append((uid, name, path, 'ASSET_MANAGER', i + 1))
    except Exception as e:
        print(f"Error in get_asset_catalogs_for_library: {e}")
    return items

def update_target_library(self, context):
    """Auto-selects the first available catalog when the library changes."""
    try:
        lib_name = self.target_library
        if lib_name and lib_name != 'LOCAL':
            libs = getattr(context.preferences.filepaths, "asset_libraries", [])
            lib_path = ""
            for lib in libs:
                if lib.name == lib_name:
                    lib_path = lib.path
                    break
            if lib_path:
                cat_file = os.path.join(lib_path, "blender_assets.cats.txt")
                if os.path.exists(cat_file):
                    with open(cat_file, "r", encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith(("#", "VERSION")):
                                continue
                            parts = line.split(":")
                            if len(parts) >= 3:
                                self.selected_catalog = parts[0]
                                return
        self.selected_catalog = 'NONE'
    except Exception as e:
        print(f"Error in update_target_library: {e}")

class URDF_AssetProperties(bpy.types.PropertyGroup):
    """
    Properties for the Asset Library System.
    """
    add_library_path: bpy.props.StringProperty(
        name="Add Library",
        description="Select Folder",
        subtype='DIR_PATH'
    )
    
    target_library: bpy.props.EnumProperty(
        name="Target Library",
        description="The Blender Asset Library folder to use",
        items=get_asset_libraries_callback,
        update=update_target_library
    )
    
    selected_catalog: bpy.props.EnumProperty(
        name="Select Catalog",
        description="Choose an existing catalog from the selected library",
        items=get_asset_catalogs_callback
    )
    
    new_catalog_name: bpy.props.StringProperty(
        name="New Catalog Name",
        description="Name for the new catalog to register in the selected library",
        default="New Robot Catalog"
    )
    
    # Kept for internal UUID lookup compatibility
    catalog_name: bpy.props.StringProperty(
        name="Catalog Name",
        description="Active catalog name (resolved from selection)",
        default=""
    )
    
    # --- Import External 3D File dedicated props ---
    import_source_filepath: bpy.props.StringProperty(
        name="Source File",
        description="Path to the external 3D file to import",
        subtype='FILE_PATH'
    )
    
    import_target_library: bpy.props.EnumProperty(
        name="Target Library",
        description="Asset library to import the file into",
        items=get_asset_libraries_callback
    )
    
    import_target_catalog: bpy.props.EnumProperty(
        name="Target Catalog",
        description="Catalog inside the selected library to assign the imported asset",
        items=lambda self, ctx: get_asset_catalogs_for_library(self.import_target_library, ctx)
    )
    
    import_file_path: bpy.props.StringProperty(
        name="File Path",
        description="Path to the external 3D file to import into the library",
        subtype='FILE_PATH'
    )
    
# ------------------------------------------------------------------------

def register():
    from . import operators, core

    # 1. Register all PropertyGroup classes FIRST
    classes = [
        URDF_TransmissionProperties, URDF_MaterialProperties, URDF_CollisionProperties, 
        URDF_InertialProperties, URDF_WrapItem, URDF_MechProps, URDF_MimicDriver, 
        URDF_JointEditorSettings, URDF_Properties, URDF_AI_Properties, 
        URDF_LightingProperties, URDF_AssetProperties
    ]
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Error registering class {cls}: {e}")

    # 2. Attach Pointer and Data Properties to Blender Types
    # Object Properties
    bpy.types.Object.urdf_mech_props = bpy.props.PointerProperty(type=URDF_MechProps)
    bpy.types.Object.urdf_dim_is_manual = bpy.props.BoolProperty(name='Manual Text Placement', default=False)
    bpy.types.Object.urdf_dim_direction = bpy.props.EnumProperty(name='Dimension Direction', items=[('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', ''), ('-X', '-X', ''), ('-Y', '-Y', ''), ('-Z', '-Z', '')], default='Z', update=operators.update_arrow_settings)
    
    # Material Properties
    bpy.types.Material.urdf_uniform_scale = bpy.props.FloatProperty(name='Uniform Scale', min=0.0001, soft_max=100.0, get=get_mat_uniform_scale, set=set_mat_uniform_scale)
    bpy.types.MaterialSlot.urdf_enabled = bpy.props.BoolProperty(name='Enable', default=True, update=operators.update_material_merge_trigger)
    
    # PoseBone Properties
    bpy.types.PoseBone.urdf_props = bpy.props.PointerProperty(type=URDF_Properties)

    # Scene Pointer Properties
    bpy.types.Scene.urdf_joint_editor_settings = bpy.props.PointerProperty(type=URDF_JointEditorSettings)
    bpy.types.Scene.urdf_ai_props = bpy.props.PointerProperty(type=URDF_AI_Properties)
    bpy.types.Scene.urdf_lighting_props = bpy.props.PointerProperty(type=URDF_LightingProperties)
    bpy.types.Scene.urdf_asset_props = bpy.props.PointerProperty(type=URDF_AssetProperties)
    bpy.types.Scene.urdf_active_rig = bpy.props.PointerProperty(type=bpy.types.Object)
    
    # Scene Panel Order & Persistence
    bpy.types.Scene.urdf_order_ai_factory = bpy.props.IntProperty(default=0)
    bpy.types.Scene.urdf_order_parts = bpy.props.IntProperty(default=1)
    bpy.types.Scene.urdf_order_architectural = bpy.props.IntProperty(default=2)
    bpy.types.Scene.urdf_order_vehicle = bpy.props.IntProperty(default=3)
    bpy.types.Scene.urdf_order_electronics = bpy.props.IntProperty(default=4)
    bpy.types.Scene.urdf_order_parametric = bpy.props.IntProperty(default=5)
    bpy.types.Scene.urdf_order_dimensions = bpy.props.IntProperty(default=6)
    bpy.types.Scene.urdf_order_materials = bpy.props.IntProperty(default=7)
    bpy.types.Scene.urdf_order_lighting = bpy.props.IntProperty(default=8)
    bpy.types.Scene.urdf_order_kinematics = bpy.props.IntProperty(default=9)
    bpy.types.Scene.urdf_order_inertial = bpy.props.IntProperty(default=10)
    bpy.types.Scene.urdf_order_collision = bpy.props.IntProperty(default=11)
    bpy.types.Scene.urdf_order_transmission = bpy.props.IntProperty(default=12)
    bpy.types.Scene.urdf_order_assets = bpy.props.IntProperty(default=13)
    bpy.types.Scene.urdf_order_export = bpy.props.IntProperty(default=14)
    bpy.types.Scene.urdf_order_preferences = bpy.props.IntProperty(default=15)

    # Scene Panel Enabled (Persistence)
    bpy.types.Scene.urdf_panel_enabled_ai_factory = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_lighting = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_parts = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_electronics = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_parametric = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_panel_enabled_dimensions = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_panel_enabled_materials = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_kinematics = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_inertial = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_collision = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_transmission = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_export = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_assets = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_panel_enabled_architectural = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_panel_enabled_vehicle = bpy.props.BoolProperty(default=True)

    # Scene Panel Show (Fold State)
    bpy.types.Scene.urdf_show_panel_ai_factory = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_show_panel_parts = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_show_panel_electronics = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_parametric = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_dimensions = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_materials = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_kinematics = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_inertial = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_collision = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_transmission = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_export = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_preferences = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_show_panel_assets = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.urdf_show_panel_architectural = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_show_panel_vehicle = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.urdf_show_panel_lighting = bpy.props.BoolProperty(default=False)

    # Global UI Settings
    bpy.types.Scene.urdf_auto_collapse_panels = bpy.props.BoolProperty(name="Auto-Collapse Other Panels", default=False)
    bpy.types.Scene.urdf_viz_gizmos = bpy.props.BoolProperty(name="Show Gizmos", default=True, update=core.update_all_gizmos)
    bpy.types.Scene.urdf_show_bones = bpy.props.BoolProperty(name="Show Bones", default=True, update=core.update_global_bones)
    bpy.types.Scene.urdf_text_placement_mode = bpy.props.BoolProperty(name="Text Placement Mode", default=False)
    bpy.types.Scene.urdf_hook_placement_mode = bpy.props.BoolProperty(name="Hook Placement Mode", default=False)
    bpy.types.Scene.urdf_placement_mode = bpy.props.BoolProperty(name="Joint Placement Mode", default=False)
    bpy.types.Scene.urdf_use_generation_cage = bpy.props.BoolProperty(name="Use Cage", default=False)
    bpy.types.Scene.urdf_generation_cage_size = bpy.props.FloatProperty(name="Cage Size", default=0.5, min=0.001, unit='LENGTH', description="The maximum dimension (bounding box) of the generated part")
    bpy.types.Scene.urdf_active_rig = bpy.props.PointerProperty(type=bpy.types.Object)
    bpy.types.Scene.urdf_gizmo_style = bpy.props.EnumProperty(items=GIZMO_STYLES, default='DEFAULT', update=core.update_all_gizmos)
    bpy.types.Scene.urdf_part_category = bpy.props.EnumProperty(items=MECH_CATEGORIES_SORTED, default='BASIC_JOINT', update=core.update_category_enum)
    bpy.types.Scene.urdf_part_type = bpy.props.EnumProperty(items=core.get_mech_types_callback)
    bpy.types.Scene.urdf_electronics_category = bpy.props.EnumProperty(items=ELECTRONICS_CATEGORIES, default='MOTOR', update=core.update_electronics_category_enum)
    bpy.types.Scene.urdf_electronics_type = bpy.props.EnumProperty(items=core.get_electronics_types_callback)
    bpy.types.Scene.urdf_vehicle_type = bpy.props.EnumProperty(items=VEHICLE_TYPES, default='CAR')
    bpy.types.Scene.urdf_architectural_type = bpy.props.EnumProperty(items=ARCHITECTURAL_TYPES, default='WALL')
    
    # Kinematics Properties
    bpy.types.Scene.urdf_cursor_local_pos = bpy.props.FloatVectorProperty(name="Local Pos", subtype='TRANSLATION', size=3, update=core.update_local_cursor_from_tool)
    bpy.types.Scene.urdf_bone_mode = bpy.props.EnumProperty(items=BONE_MODES, default='INDIVIDUAL')
    bpy.types.Scene.urdf_bone_axis = bpy.props.EnumProperty(items=BONE_AXES, default='AUTO')
    
    # Dimensions & Measuring Scene Properties
    # Dimensions & Measuring Properties (on Scene for global/defaults, on Object for per-dim)
    # Note: These scene properties now serve as defaults for new dimensions
    bpy.types.Scene.urdf_dim_arrow_scale = bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.001, soft_max=5.0)
    bpy.types.Scene.urdf_dim_text_scale = bpy.props.FloatProperty(name="Text Scale", default=0.1, min=0.001, soft_max=5.0)
    bpy.types.Scene.urdf_dim_unit_display = bpy.props.EnumProperty(
        name="Unit Display", default='SCENE',
        items=[('SCENE', 'Scene Units', ''), ('METRIC', 'Metric (m)', ''), ('IMPERIAL', 'Imperial (ft)', ''), ('MM', 'Millimeters', ''), ('CM', 'Centimeters', '')])
    bpy.types.Scene.urdf_text_color = bpy.props.FloatVectorProperty(
        name="Text Color", subtype='COLOR', size=4, min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 1.0), update=update_text_color)
    bpy.types.Scene.urdf_dim_line_thickness = bpy.props.FloatProperty(name="Line Thickness", default=0.005, min=0.0001, soft_max=0.1)
    bpy.types.Scene.urdf_dim_offset = bpy.props.FloatProperty(name="Offset", default=0.05, min=0.0, soft_max=1.0)
    bpy.types.Scene.urdf_dim_extension = bpy.props.FloatProperty(name="Extension", default=0.02, min=0.0, soft_max=0.5)
    bpy.types.Scene.urdf_dim_axis = bpy.props.EnumProperty(
        name="Axis", items=[('X', 'X Axis', ''), ('Y', 'Y Axis', ''), ('Z', 'Z Axis', ''), ('ALL', 'All Axes', '')], default='ALL'
    )
    
    bpy.types.Object.urdf_mech_props = bpy.props.PointerProperty(type=URDF_MechProps)
    bpy.types.Object.urdf_dim_is_manual = bpy.props.BoolProperty(name='Manual Text Placement', default=False)
    bpy.types.Object.urdf_dim_direction = bpy.props.EnumProperty(name='Dimension Direction', items=[('X', 'X', ''), ('Y', 'Y', ''), ('Z', 'Z', ''), ('-X', '-X', ''), ('-Y', '-Y', ''), ('-Z', '-Z', '')], default='Z', update=operators.update_arrow_settings)
    
    # Per-Object Dimension Properties
    bpy.types.Object.urdf_dim_arrow_scale = bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.001, soft_max=5.0, update=operators.update_arrow_settings)
    bpy.types.Object.urdf_dim_text_scale = bpy.props.FloatProperty(name="Text Scale", default=0.1, min=0.001, soft_max=5.0, update=operators.update_arrow_settings)
    bpy.types.Object.urdf_dim_unit_display = bpy.props.EnumProperty(
        name="Unit Display", default='SCENE',
        items=[('SCENE', 'Scene Units', ''), ('METRIC', 'Metric (m)', ''), ('IMPERIAL', 'Imperial (ft)', ''), ('MM', 'Millimeters', ''), ('CM', 'Centimeters', '')],
        update=operators.update_dimensions_trigger)
    bpy.types.Object.urdf_dim_text_color = bpy.props.FloatVectorProperty(
        name="Label Color", subtype='COLOR', size=4, min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 1.0), update=update_text_color)
    bpy.types.Object.urdf_dim_line_thickness = bpy.props.FloatProperty(name="Line Thickness", default=0.005, min=0.0001, soft_max=0.1, update=operators.update_dimensions_trigger)
    bpy.types.Object.urdf_dim_offset = bpy.props.FloatProperty(name="Offset from Object", default=0.05, min=0.0, soft_max=1.0, update=operators.update_dimensions_trigger)
    bpy.types.Object.urdf_dim_extension = bpy.props.FloatProperty(name="End Extension", default=0.02, min=0.0, soft_max=0.5, update=operators.update_dimensions_trigger)
    bpy.types.Object.urdf_dim_length = bpy.props.FloatProperty(name="Length", default=0.0, min=0.0, unit='LENGTH', update=operators.update_dimension_length)
    
    bpy.types.Material.urdf_uniform_scale = bpy.props.FloatProperty(name='Uniform Scale', min=0.0001, soft_max=100.0, get=get_mat_uniform_scale, set=set_mat_uniform_scale)
    bpy.types.MaterialSlot.urdf_enabled = bpy.props.BoolProperty(name='Enable', default=True, update=operators.update_material_merge_trigger)
    
    bpy.types.PoseBone.urdf_props = bpy.props.PointerProperty(type=URDF_Properties)

def unregister():
    # 1. Clean up Object and Scene Properties (Reverse Order)
    try:
        # Systematic cleanup of Object properties
        obj_props = [
            "urdf_mech_props", "urdf_dim_is_manual", "urdf_dim_direction",
            "urdf_dim_arrow_scale", "urdf_dim_text_scale", "urdf_dim_unit_display",
            "urdf_dim_text_color", "urdf_dim_line_thickness", "urdf_dim_offset", "urdf_dim_extension",
            "urdf_dim_length"
        ]
        for prop in obj_props:
            if hasattr(bpy.types.Object, prop):
                delattr(bpy.types.Object, prop)
        
        if hasattr(bpy.types.Material, "urdf_uniform_scale"):
            del bpy.types.Material.urdf_uniform_scale
        if hasattr(bpy.types.MaterialSlot, "urdf_enabled"):
            del bpy.types.MaterialSlot.urdf_enabled
        if hasattr(bpy.types.PoseBone, "urdf_props"):
            del bpy.types.PoseBone.urdf_props
        
        del bpy.types.Scene.urdf_joint_editor_settings
        del bpy.types.Scene.urdf_ai_props
        del bpy.types.Scene.urdf_lighting_props
        del bpy.types.Scene.urdf_asset_props
        del bpy.types.Scene.urdf_active_rig
        
        # Systematic cleanup of all Scene properties
        scene_props = [
            "urdf_panel_enabled_ai_factory", "urdf_panel_enabled_lighting", "urdf_panel_enabled_parts",
            "urdf_panel_enabled_electronics", "urdf_panel_enabled_parametric", "urdf_panel_enabled_dimensions",
            "urdf_panel_enabled_materials", "urdf_panel_enabled_kinematics", "urdf_panel_enabled_inertial",
            "urdf_panel_enabled_collision", "urdf_panel_enabled_transmission", "urdf_panel_enabled_export",
            "urdf_panel_enabled_assets", "urdf_show_panel_ai_factory", "urdf_show_panel_parts",
            "urdf_show_panel_electronics", "urdf_show_panel_parametric", "urdf_show_panel_dimensions",
            "urdf_show_panel_materials", "urdf_show_panel_kinematics", "urdf_show_panel_inertial",
            "urdf_show_panel_collision", "urdf_show_panel_transmission", "urdf_show_panel_export",
            "urdf_show_panel_preferences", "urdf_show_panel_assets", "urdf_show_panel_lighting", "urdf_show_panel_architectural",
            "urdf_auto_collapse_panels", "urdf_viz_gizmos", "urdf_show_bones", "urdf_use_generation_cage",
            "urdf_generation_cage_size", "urdf_gizmo_style", "urdf_part_category", "urdf_electronics_category",
            "urdf_placement_mode", "urdf_text_placement_mode", "urdf_hook_placement_mode",
            "urdf_cursor_local_pos", "urdf_bone_mode", "urdf_bone_axis",
            "urdf_dim_direction", "urdf_dim_arrow_scale", "urdf_dim_text_scale", "urdf_dim_unit_display",
            "urdf_text_color", "urdf_dim_line_thickness", "urdf_dim_offset", "urdf_dim_extension",
            "urdf_dim_axis"
        ]
        for prop in scene_props:
            if hasattr(bpy.types.Scene, prop):
                delattr(bpy.types.Scene, prop)
                
    except Exception as e:
        print(f"Error during property deletion: {e}")
        
    # 2. Unregister classes in REVERSE order
    classes = [
        URDF_TransmissionProperties, URDF_MaterialProperties, URDF_CollisionProperties, 
        URDF_InertialProperties, URDF_WrapItem, URDF_MechProps, URDF_MimicDriver, 
        URDF_JointEditorSettings, URDF_Properties, URDF_AI_Properties, 
        URDF_LightingProperties, URDF_AssetProperties
    ]
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

