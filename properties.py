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
import math
import mathutils
import re
import os
import json
import xml.etree.ElementTree as ET
from typing import List, Tuple, Optional, Set, Any, Dict
from . import config
from .config import *

# ------------------------------------------------------------------------
#   Update Callbacks
# ------------------------------------------------------------------------

def update_mesh_wrapper(self, context: bpy.types.Context):
    """Lean dispatcher to generators module."""
    from . import generators
    generators.update_mesh_wrapper(self, context)

def update_radius_prop(self, context: bpy.types.Context):
    """Special handler for synced radius properties."""
    r = self.radius
    if self.category == 'GEAR': r = self.gear_radius
    elif self.category == 'WHEEL': r = self.wheel_radius
    elif self.category == 'PULLEY': r = self.pulley_radius
    elif self.category == 'BASIC_JOINT': r = self.joint_radius
    
    self.last_radius = r
    update_mesh_wrapper(self, context)

def dispatch_apply_joint_settings():
    bpy.ops.fcd.apply_joint_settings()
    return None

def dispatch_apply_bone_constraints():
    bpy.ops.fcd.apply_bone_constraints()
    return None

def update_joint_tool_live(self, context):
    """
    Timer-based dispatcher for the joint tool.
    Ensures safe execution of operators during property update callbacks.
    AI Editor Note: Using named functions for timers prevents redundant 
    registrations during rapid property changes (like slider dragging).
    """
    from . import core
    if isinstance(self.id_data, bpy.types.Scene):
        if not core._joint_editor_update_guard:
            # Using a named function for the timer ensures we don't stack lambdas
            bpy.app.timers.register(dispatch_apply_joint_settings, first_interval=0.01)
    else:
        # Individual bone update
        if not core._prop_update_guard:
            if hasattr(self.id_data, "pose") and context.mode == 'POSE':
                # Transitioning to a timer avoids "readonly mode" errors.
                # Named function prevents multiple identical timers.
                bpy.app.timers.register(dispatch_apply_bone_constraints, first_interval=0.01)

def update_placement_mode_wrapper(self, context):
    """Lean dispatcher for placement mode state change."""
    from . import core
    core.toggle_placement_parenting(self, context)

def update_text_color(self, context):
    """Updates dimension material colors."""
    if hasattr(self, "id_data") and self.id_data.get("fcd_is_dimension"):
        from . import core
        core.get_or_create_text_material(self.id_data)
        self.id_data.update_tag()

def update_arrow_settings_timer(self, context):
    """Dispatches arrow setting update via timer with a single-queue guard."""
    from . import core
    if getattr(core, "_dim_timer_queued", False): return
    core._dim_timer_queued = True
    
    # AI Editor Note: Specifically trigger the heavy role swap logic 
    # IF this is the property being changed. self is the PropertyGroup.
    obj = self.id_data
    if obj:
         # Note: sync_dimension_flipping internally handles the check if role swap is needed
         core.sync_dimension_flipping(obj)

    def dispatch():
        core._dim_timer_queued = False
        obj = self.id_data
        if obj: core.update_arrow_settings(obj)
        return None
    bpy.app.timers.register(dispatch, first_interval=0.03)

def update_dimension_length_timer(self, context):
    """Dispatches length update via timer with a single-queue guard."""
    from . import core
    if getattr(core, "_dim_timer_queued", False): return
    core._dim_timer_queued = True
    
    if hasattr(self, "is_manual"):
        self.is_manual = True
        
    def dispatch():
        core._dim_timer_queued = False
        obj = self.id_data
        if obj: core.update_dimension_length(obj)
        return None
    bpy.app.timers.register(dispatch, first_interval=0.03)

def update_cursor_local_wrapper(self, context):
    """Lean dispatcher to core module for cursor tool."""
    from . import core
    core.update_local_cursor_from_tool(self, context)

# ------------------------------------------------------------------------
#   Property Group Definitions (FCD PG Mandate)
# ------------------------------------------------------------------------

class FCD_PG_Transmission_Properties(bpy.types.PropertyGroup):
    type: bpy.props.StringProperty(name="Type", default="transmission_interface/SimpleTransmission")
    joint: bpy.props.StringProperty(name="Joint")
    hardware_interface: bpy.props.StringProperty(name="Hardware Interface", default="hardware_interface/EffortJointInterface")
    mechanical_reduction: bpy.props.FloatProperty(name="Mechanical Reduction", default=1.0)

class FCD_PG_Material_Properties(bpy.types.PropertyGroup):
    color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', default=(0.8, 0.8, 0.8, 1.0), size=4, min=0.0, max=1.0)
    texture: bpy.props.PointerProperty(name="Texture", type=bpy.types.Image)

class FCD_PG_Slinky_Hook(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Hook Name")
    target: bpy.props.PointerProperty(type=bpy.types.Object, name="Target")

class FCD_PG_Wrap_Item(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Item Name")
    obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Object")

class FCD_PG_Collision_Properties(bpy.types.PropertyGroup):
    shape: bpy.props.EnumProperty(name="Shape", items=[('BOX', "Box", ""), ('CYLINDER', "Cylinder", ""), ('SPHERE', "Sphere", ""), ('MESH', "Mesh", "")], default='MESH')
    collision_object: bpy.props.PointerProperty(name="Collision Object", type=bpy.types.Object)

class FCD_PG_Inertial_Properties(bpy.types.PropertyGroup):
    mass: bpy.props.FloatProperty(name="Mass", default=1.0, min=0.0)
    center_of_mass: bpy.props.FloatVectorProperty(name="Center of Mass", subtype='TRANSLATION', unit='LENGTH', size=3)
    ixx: bpy.props.FloatProperty(name="Ixx", default=1.0)
    iyy: bpy.props.FloatProperty(name="Iyy", default=1.0)
    izz: bpy.props.FloatProperty(name="Izz", default=1.0)
    ixy: bpy.props.FloatProperty(name="Ixy", default=0.0)
    ixz: bpy.props.FloatProperty(name="Ixz", default=0.0)
    iyz: bpy.props.FloatProperty(name="Iyz", default=0.0)

class FCD_PG_Wrap_Item(bpy.types.PropertyGroup):
    target: bpy.props.PointerProperty(type=bpy.types.Object, name="Wrap Object")

class FCD_PG_Dimension_Props(bpy.types.PropertyGroup):
    """
    Parametric properties for dimension labels and arrow heads.
    Uses timer-based updates to maintain UI responsiveness.
    """
    arrow_scale: bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.001, update=update_arrow_settings_timer)
    text_scale: bpy.props.FloatProperty(name="Text Size", default=0.1, min=0.0, update=update_arrow_settings_timer)
    line_thickness: bpy.props.FloatProperty(name="Line Thickness", default=0.002, min=0.0, unit='LENGTH', update=update_arrow_settings_timer)
    offset: bpy.props.FloatProperty(name="Offset from Target", default=0.1, unit='LENGTH', update=update_arrow_settings_timer)
    text_color: bpy.props.FloatVectorProperty(name="Label Color", subtype='COLOR', default=(0.0, 0.0, 0.0, 1.0), size=4, min=0.0, max=1.0, update=update_text_color)
    unit_display: bpy.props.EnumProperty(name="Units", items=[('METERS', "Meters (m)", ""), ('MM', "Millimeters (mm)", "")], default='METERS', update=update_dimension_length_timer)
    length: bpy.props.FloatProperty(name="Line Length", default=1.0, unit='LENGTH', update=update_dimension_length_timer)
    direction: bpy.props.EnumProperty(name="Direction", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], default='Z', update=update_arrow_settings_timer)
    is_flipped: bpy.props.BoolProperty(name="Flip Target Roles", default=False, update=update_arrow_settings_timer)
    use_extension_lines: bpy.props.BoolProperty(name="Use Extension Lines", default=True, update=update_arrow_settings_timer)
    is_manual: bpy.props.BoolProperty(name="Manual Mode", default=False)
    align_x: bpy.props.BoolProperty(name="+X", default=False, update=update_arrow_settings_timer)
    align_nx: bpy.props.BoolProperty(name="-X", default=False, update=update_arrow_settings_timer)
    align_y: bpy.props.BoolProperty(name="+Y", default=False, update=update_arrow_settings_timer)
    align_ny: bpy.props.BoolProperty(name="-Y", default=False, update=update_arrow_settings_timer)
    align_z: bpy.props.BoolProperty(name="+Z", default=False, update=update_arrow_settings_timer)
    align_nz: bpy.props.BoolProperty(name="-Z", default=False, update=update_arrow_settings_timer)
    flip_text: bpy.props.BoolProperty(name="Flip Text", default=False, update=update_arrow_settings_timer)
    text_rotation: bpy.props.FloatVectorProperty(name="Text Rotation", subtype='EULER', size=3, default=(0.0, 0.0, 0.0), update=update_arrow_settings_timer)
    
    # Hidden Persistent State (For Offset Coherence)
    target_x: bpy.props.FloatProperty(name="Target Transverse X", default=0.0)
    target_y: bpy.props.FloatProperty(name="Target Transverse Y", default=0.0)
    text_alignment: bpy.props.EnumProperty(
        name="Text Alignment",
        items=[('LEFT', "Left", ""), ('CENTER', "Center", ""), ('RIGHT', "Right", "")],
        default='CENTER',
        update=update_arrow_settings_timer
    )

class FCD_PG_Mech_Props(bpy.types.PropertyGroup):
    is_part: bpy.props.BoolProperty(default=False)
    category: bpy.props.EnumProperty(name="Category", items=ALL_CATEGORIES_SORTED, update=update_mesh_wrapper)
    
    # Types
    type_gear: bpy.props.EnumProperty(name="Type", items=GEAR_TYPES, update=update_mesh_wrapper)
    type_rack: bpy.props.EnumProperty(name="Type", items=RACK_TYPES, update=update_mesh_wrapper)
    type_basic_shape: bpy.props.EnumProperty(name="Type", items=BASIC_SHAPE_TYPES, update=update_mesh_wrapper)
    type_pulley: bpy.props.EnumProperty(name="Type", items=PULLEY_TYPES, update=update_mesh_wrapper)
    type_rope: bpy.props.EnumProperty(name="Type", items=ROPE_TYPES, update=update_mesh_wrapper)
    type_spring: bpy.props.EnumProperty(name="Type", items=SPRING_TYPES, update=update_mesh_wrapper)
    type_fastener: bpy.props.EnumProperty(name="Type", items=FASTENER_TYPES, update=update_mesh_wrapper)
    type_chain: bpy.props.EnumProperty(name="Type", items=CHAIN_TYPES, update=update_mesh_wrapper)
    type_wheel: bpy.props.EnumProperty(name="Type", items=WHEEL_TYPES, update=update_mesh_wrapper)
    type_basic_joint: bpy.props.EnumProperty(name="Type", items=BASIC_JOINT_TYPES, update=update_mesh_wrapper)
    type_electronics: bpy.props.EnumProperty(name="Type", items=ALL_ELECTRONICS_TYPES, update=update_mesh_wrapper)
    type_architectural: bpy.props.EnumProperty(name="Type", items=ARCHITECTURAL_TYPES, update=update_mesh_wrapper)
    type_vehicle: bpy.props.EnumProperty(name="Type", items=VEHICLE_TYPES, update=update_mesh_wrapper)

    # 1. GEARS
    gear_radius: bpy.props.FloatProperty(name="Gear Radius", default=0.05, min=0.001, unit='LENGTH', update=update_radius_prop)
    gear_width: bpy.props.FloatProperty(name="Gear Width", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    gear_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=24, min=3, update=update_mesh_wrapper)
    gear_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.005, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    gear_tooth_taper: bpy.props.FloatProperty(name="Tooth Taper", default=0.8, min=0.0, max=1.5, update=update_mesh_wrapper)
    gear_bore_radius: bpy.props.FloatProperty(name="Bore Radius", default=0.0, min=0.0, unit='LENGTH', update=update_mesh_wrapper)
    gear_outer_radius: bpy.props.FloatProperty(name="Outer Radius (Ring)", default=0.06, min=0.001, unit='LENGTH', update=update_mesh_wrapper)

    # 2. RACKS
    rack_width: bpy.props.FloatProperty(name="Rack Width", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rack_height: bpy.props.FloatProperty(name="Rack Height", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rack_length: bpy.props.FloatProperty(name="Rack Length", default=0.2, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rack_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=40, min=1, update=update_mesh_wrapper)
    rack_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.005, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)

    # 3. FASTENERS
    fastener_radius: bpy.props.FloatProperty(name="Fastener Radius", default=0.004, min=0.0005, unit='LENGTH', update=update_mesh_wrapper)
    fastener_length: bpy.props.FloatProperty(name="Fastener Length", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)

    # 4. SPRINGS & DAMPERS
    spring_radius: bpy.props.FloatProperty(name="Spring Radius", default=0.015, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    spring_wire_thickness: bpy.props.FloatProperty(name="Wire Thickness", default=0.002, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    spring_turns: bpy.props.IntProperty(name="Turns", default=10, min=1, update=update_mesh_wrapper)

    # 1. GEARS & RACKS EXTENDED
    tooth_spacing: bpy.props.FloatProperty(name="Tooth Spacing", default=0.0, min=0.0, update=update_mesh_wrapper)
    twist: bpy.props.FloatProperty(name="Twist Rate", default=0.0, update=update_mesh_wrapper)
    bore_type: bpy.props.EnumProperty(name="Bore Type", items=[('ROUND', "Round", ""), ('SQUARE', "Square", ""), ('D-SHAFT', "D-Shaft", ""), ('HEX', "Hex", "")], default='ROUND', update=update_mesh_wrapper)
    
    # 4. SPRINGS & DAMPERS EXTENDED
    slinky_hooks: bpy.props.CollectionProperty(type=FCD_PG_Slinky_Hook)
    slinky_active_index: bpy.props.IntProperty(default=0)
    
    # 5. CHAINS & BELTS EXTENDED
    chain_drive_target: bpy.props.PointerProperty(type=bpy.types.Object, name="Drive Source")
    chain_drive_ratio: bpy.props.FloatProperty(name="Drive Ratio", default=1.0)
    chain_drive_invert: bpy.props.BoolProperty(name="Invert Drive", default=False)
    wrap_picker: bpy.props.PointerProperty(type=bpy.types.Object, name="Wrap Object")
    chain_wrap_items: bpy.props.CollectionProperty(type=FCD_PG_Wrap_Item)
    chain_active_index: bpy.props.IntProperty(default=0)

    # 6. WHEELS EXTENDED
    wheel_side_pattern: bpy.props.EnumProperty(name="Side Pattern", items=[('NONE', "None", ""), ('HOLES', "Holes", ""), ('SPOKES', "Spokes", "")], default='NONE', update=update_mesh_wrapper)
    wheel_tread_pattern: bpy.props.EnumProperty(name="Tread Pattern", items=[('NONE', "None", ""), ('LINES', "Lines", ""), ('BLOCKS', "Blocks", "")], default='NONE', update=update_mesh_wrapper)
    wheel_pattern_spacing: bpy.props.FloatProperty(name="Pattern Spacing", default=0.1, update=update_mesh_wrapper)
    wheel_pattern_depth: bpy.props.FloatProperty(name="Pattern Depth", default=0.005, update=update_mesh_wrapper)

    # 11. BASIC SHAPE PROPERTIES
    shape_size: bpy.props.FloatProperty(name="Size", default=1.0, update=update_mesh_wrapper)
    shape_length_x: bpy.props.FloatProperty(name="Length X", default=1.0, update=update_mesh_wrapper)
    shape_width_y: bpy.props.FloatProperty(name="Width Y", default=1.0, update=update_mesh_wrapper)
    shape_height_z: bpy.props.FloatProperty(name="Height Z", default=1.0, update=update_mesh_wrapper)
    shape_radius: bpy.props.FloatProperty(name="Radius", default=1.0, update=update_mesh_wrapper)
    shape_vertices: bpy.props.IntProperty(name="Vertices", default=32, min=3, update=update_mesh_wrapper)
    shape_height: bpy.props.FloatProperty(name="Height", default=2.0, update=update_mesh_wrapper)
    shape_segments: bpy.props.IntProperty(name="Segments", default=32, min=3, update=update_mesh_wrapper)
    shape_subdivisions: bpy.props.IntProperty(name="Subdivisions", default=2, min=1, update=update_mesh_wrapper)
    shape_major_radius: bpy.props.FloatProperty(name="Major Radius", default=1.0, update=update_mesh_wrapper)
    shape_tube_radius: bpy.props.FloatProperty(name="Tube Radius", default=0.25, update=update_mesh_wrapper)
    shape_horizontal_segments: bpy.props.IntProperty(name="Horizontal Segments", default=48, min=3, update=update_mesh_wrapper)
    shape_vertical_segments: bpy.props.IntProperty(name="Vertical Segments", default=12, min=3, update=update_mesh_wrapper)

    # 12. ARCHITECTURAL PROPERTIES
    wall_thickness: bpy.props.FloatProperty(name="Wall Thickness", default=0.2, min=0.01, unit='LENGTH', update=update_mesh_wrapper)
    window_frame_thickness: bpy.props.FloatProperty(name="Frame Thickness", default=0.05, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    glass_thickness: bpy.props.FloatProperty(name="Glass Thickness", default=0.01, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    step_count: bpy.props.IntProperty(name="Step Count", default=12, min=1, update=update_mesh_wrapper)
    step_height: bpy.props.FloatProperty(name="Step Riser", default=0.18, min=0.01, unit='LENGTH', update=update_mesh_wrapper)
    step_depth: bpy.props.FloatProperty(name="Step Tread", default=0.28, min=0.01, unit='LENGTH', update=update_mesh_wrapper)

    # ... (rest of the properties continue)
    
    # Dynamic/Damper Specific
    height: bpy.props.FloatProperty(name="Housing Height", default=0.1, unit='LENGTH', update=update_mesh_wrapper)
    length: bpy.props.FloatProperty(name="Current Length", default=0.2, unit='LENGTH', update=update_mesh_wrapper)
    radius: bpy.props.FloatProperty(name="Housing Radius", default=0.05, unit='LENGTH', update=update_mesh_wrapper)
    teeth: bpy.props.IntProperty(name="Segments/Turns", default=12, update=update_mesh_wrapper)
    tooth_depth: bpy.props.FloatProperty(name="Wire/Rod Radius", default=0.005, unit='LENGTH', update=update_mesh_wrapper)
    outer_radius: bpy.props.FloatProperty(name="Outer Radius", default=0.06, unit='LENGTH', update=update_mesh_wrapper)
    bore_radius: bpy.props.FloatProperty(name="Bore Radius", default=0.03, unit='LENGTH', update=update_mesh_wrapper)
    damper_seat_radius: bpy.props.FloatProperty(name="Seat Radius", default=0.08, unit='LENGTH', update=update_mesh_wrapper)
    damper_seat_thickness: bpy.props.FloatProperty(name="Seat Thickness", default=0.02, unit='LENGTH', update=update_mesh_wrapper)
    
    # 5. CHAINS & BELTS
    chain_pitch: bpy.props.FloatProperty(name="Chain Pitch", default=0.0127, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    chain_roller_radius: bpy.props.FloatProperty(name="Roller Radius", default=0.004, min=0.0005, unit='LENGTH', update=update_mesh_wrapper)
    chain_roller_length: bpy.props.FloatProperty(name="Roller Length", default=0.008, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    chain_curve_res: bpy.props.IntProperty(name="Curve Resolution", default=12, min=1, max=64, update=update_mesh_wrapper)
    chain_plate_height: bpy.props.FloatProperty(name="Plate Height", default=0.01, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    chain_plate_thickness: bpy.props.FloatProperty(name="Plate Thickness", default=0.0015, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    belt_width: bpy.props.FloatProperty(name="Belt Width", default=0.015, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    belt_thickness: bpy.props.FloatProperty(name="Belt Thickness", default=0.002, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)

    # 6. WHEELS
    wheel_radius: bpy.props.FloatProperty(name="Wheel Radius", default=0.05, min=0.001, unit='LENGTH', update=update_radius_prop)
    wheel_width: bpy.props.FloatProperty(name="Wheel Width", default=0.04, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_hub_radius: bpy.props.FloatProperty(name="Hub Radius", default=0.012, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_hub_length: bpy.props.FloatProperty(name="Hub Width", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_tread_count: bpy.props.IntProperty(name="Tread Count", default=24, min=1, update=update_mesh_wrapper)
    wheel_sub_radius: bpy.props.FloatProperty(name="Sub-Radius", default=0.008, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_sub_length: bpy.props.FloatProperty(name="Sub-Length", default=0.025, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_sub_arrays: bpy.props.IntProperty(name="Roller Arrays", default=1, min=1, update=update_mesh_wrapper)
    wheel_sub_support_thickness: bpy.props.FloatProperty(name="Support Thickness", default=0.002, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_sub_support_length: bpy.props.FloatProperty(name="Support Length", default=0.005, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_axle_length: bpy.props.FloatProperty(name="Axle Length", default=0.045, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    wheel_thickness: bpy.props.FloatProperty(name="Carriage Thickness", default=0.01, min=0.001, unit='LENGTH', update=update_mesh_wrapper)

    # 7. PULLEYS
    pulley_radius: bpy.props.FloatProperty(name="Pulley Radius", default=0.03, min=0.001, unit='LENGTH', update=update_radius_prop)
    pulley_width: bpy.props.FloatProperty(name="Pulley Width", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    pulley_groove_depth: bpy.props.FloatProperty(name="Groove Depth", default=0.005, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    pulley_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=20, min=3, update=update_mesh_wrapper)

    # 8. ROPES & CABLES
    rope_radius: bpy.props.FloatProperty(name="Rope Radius", default=0.003, min=0.0005, unit='LENGTH', update=update_mesh_wrapper)
    rope_length: bpy.props.FloatProperty(name="Rope Length", default=0.5, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rope_strands: bpy.props.IntProperty(name="Strands", default=7, min=1, update=update_mesh_wrapper)

    # 9. BASIC JOINTS
    joint_width: bpy.props.FloatProperty(name="Joint Width", default=0.08, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_radius: bpy.props.FloatProperty(name="Joint Radius", default=0.03, min=0.001, unit='LENGTH', update=update_radius_prop)
    joint_pin_radius: bpy.props.FloatProperty(name="Pin Radius", default=0.007, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_pin_length: bpy.props.FloatProperty(name="Pin Length", default=0.06, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_sub_size: bpy.props.FloatProperty(name="Sub-Size/Overhang", default=0.001, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    
    # Joint Generator Tracking Pointers (AI Added for Stability)
    joint_stator_obj: bpy.props.PointerProperty(name="Stator Object", type=bpy.types.Object)
    joint_rotor_obj: bpy.props.PointerProperty(name="Rotor Object", type=bpy.types.Object)
    joint_screw_obj: bpy.props.PointerProperty(name="Screw Object", type=bpy.types.Object)
    joint_pin_obj: bpy.props.PointerProperty(name="Pin Object", type=bpy.types.Object)
    joint_sub_thickness: bpy.props.FloatProperty(name="Sub-Thickness", default=0.001, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    joint_frame_width: bpy.props.FloatProperty(name="Frame Width", default=0.06, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_frame_length: bpy.props.FloatProperty(name="Frame Length", default=0.08, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_carriage_width: bpy.props.FloatProperty(name="Carriage Width", default=0.08, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_carriage_thickness: bpy.props.FloatProperty(name="Carriage Thickness", default=0.01, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rotor_arm_length: bpy.props.FloatProperty(name="Rotor Arm Length", default=0.194, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    rotor_arm_width: bpy.props.FloatProperty(name="Rotor Arm Width", default=0.001, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)
    rotor_arm_height: bpy.props.FloatProperty(name="Rotor Arm Height", default=0.001, min=0.0001, unit='LENGTH', update=update_mesh_wrapper)

    # 10. ELECTRONICS / CONTINUOUS JOINTS
    joint_base_radius: bpy.props.FloatProperty(name="Base Radius", default=0.06, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_base_length: bpy.props.FloatProperty(name="Base Length", default=0.12, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_motor_height: bpy.props.FloatProperty(name="Motor Height", default=0.035, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    joint_motor_shaft_radius: bpy.props.FloatProperty(name="Shaft Radius", default=0.01, min=0.0005, unit='LENGTH', update=update_mesh_wrapper)
    joint_motor_shaft_length: bpy.props.FloatProperty(name="Shaft Length", default=0.02, min=0.001, unit='LENGTH', update=update_mesh_wrapper)
    
    # 11. CAMERA SETUP & ANIMATION
    camera_target: bpy.props.PointerProperty(name="Look At Target", type=bpy.types.Object)
    camera_path: bpy.props.PointerProperty(name="Animation Path", type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CURVE')
    camera_focal_length: bpy.props.FloatProperty(name="Focal Length", default=35.0, min=1.0, max=5000.0, update=update_mesh_wrapper)
    camera_dof_enabled: bpy.props.BoolProperty(name="Enable Depth of Field", default=False)
    camera_fstop: bpy.props.FloatProperty(name="F-Stop", default=2.8, min=0.1, max=128.0)
    camera_follow_path: bpy.props.BoolProperty(name="Follow Path", default=False)
    camera_path_offset: bpy.props.FloatProperty(name="Path Offset", default=0.0, min=-1000.0, max=1000.0)
    
    # Final Pointers
    spring_start_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    spring_end_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    instanced_link_obj: bpy.props.PointerProperty(type=bpy.types.Object)
    
    # Internal track logic
    last_radius: bpy.props.FloatProperty(default=0.0, options={'HIDDEN'})
    
    # Sub-props
    collision: bpy.props.PointerProperty(type=FCD_PG_Collision_Properties)
    inertial: bpy.props.PointerProperty(type=FCD_PG_Inertial_Properties)
    material: bpy.props.PointerProperty(type=FCD_PG_Material_Properties)

class FCD_PG_Mimic_Driver(bpy.types.PropertyGroup):
    target_bone: bpy.props.StringProperty(name="Target")
    ratio: bpy.props.FloatProperty(name="Ratio", default=1.0)

class FCD_PG_Kinematic_Props(bpy.types.PropertyGroup):
    joint_type: bpy.props.EnumProperty(
        items=[('none', "None", ""), ('base', "Base", ""), ('fixed', "Fixed", ""), ('revolute', "Revolute", ""), ('continuous', "Continuous", ""), ('prismatic', "Linear", ""), ('spherical', "Spherical", "")], 
        default='none',
        update=update_joint_tool_live
    )
    axis_enum: bpy.props.EnumProperty(
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], 
        default='Z',
        update=update_joint_tool_live
    )
    joint_radius: bpy.props.FloatProperty(name="Joint Radius", default=0.05, min=0.0, unit='LENGTH', update=update_joint_tool_live)
    gizmo_radius: bpy.props.FloatProperty(name="Gizmo Radius", default=0.1, min=0.0, unit='LENGTH', update=update_joint_tool_live)
    lower_limit: bpy.props.FloatProperty(name="Lower", default=-90.0, update=update_joint_tool_live)
    upper_limit: bpy.props.FloatProperty(name="Upper", default=90.0, update=update_joint_tool_live)
    ik_chain_length: bpy.props.IntProperty(name="IK Chain Length", default=0, min=0, max=255, update=update_joint_tool_live)
    ratio_value: bpy.props.FloatProperty(name="Ratio", default=1.0)
    ratio_target_bone: bpy.props.StringProperty(name="Target Bone")
    ratio_ref_bone: bpy.props.StringProperty(name="Ref Bone")
    ratio_invert: bpy.props.BoolProperty(name="Invert", default=False)
    mimic_drivers: bpy.props.CollectionProperty(type=FCD_PG_Mimic_Driver)

class FCD_PG_AI_Props(bpy.types.PropertyGroup):
    ai_source: bpy.props.EnumProperty(
        name="Source", 
        items=[
            ('API', "Cloud API (Standard)", ""), 
            ('LOCAL', "Local LLM / Scripting", "")
        ], 
        default='API'
    )
    api_key: bpy.props.StringProperty(name="API Key", subtype='PASSWORD')
    api_prompt: bpy.props.StringProperty(name="Detailed Prompt", default="Generate a simple robot.")

class FCD_PG_Lighting_Props(bpy.types.PropertyGroup):
    light_preset: bpy.props.EnumProperty(name="Preset", items=[('STUDIO', "Studio", ""), ('OUTDOOR', "Outdoor", ""), ('EMPTY', "Ambient", "")], default='STUDIO')
    background_color: bpy.props.FloatVectorProperty(name="Background", subtype='COLOR', size=4, default=(0.04, 0.04, 0.04, 1.0))
    base_color: bpy.props.FloatVectorProperty(name="Tint", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0))

class FCD_PG_Asset_Props(bpy.types.PropertyGroup):
    target_library: bpy.props.StringProperty(name="Library Path", description="Library folder used for marking and importing assets.")
    selected_catalog: bpy.props.StringProperty(name="Catalog", description="Choose a catalog folder within the selected library.")
    
    # Path/Management properties used in sidebars/popups
    add_library_path: bpy.props.StringProperty(name="New Library Path", description="Path to a folder to be added as a new Asset Library.")
    new_catalog_name: bpy.props.StringProperty(name="Catalog Name", description="Name for the new asset catalog folder.")
    
    # Batch Import settings
    import_source_filepath: bpy.props.StringProperty(name="Import File", description="Select a 3D file (.blend, .fbx, .glb) to import.", subtype='FILE_PATH')
    import_target_library: bpy.props.StringProperty(name="Target Library", description="Library where the imported file will be registered.")
    import_target_catalog: bpy.props.StringProperty(name="Target Catalog", description="Catalog folder where the imported file will be added.")

class FCD_ExportItem(bpy.types.PropertyGroup):
    """Item for the export list"""
    rig: bpy.props.PointerProperty(type=bpy.types.Object, name="Rig")

# ------------------------------------------------------------------------
#   Registration
# ------------------------------------------------------------------------

CLASSES = [
    FCD_PG_Transmission_Properties, FCD_PG_Material_Properties, FCD_PG_Collision_Properties,
    FCD_PG_Inertial_Properties, FCD_PG_Wrap_Item, FCD_PG_Slinky_Hook, FCD_PG_Mech_Props, FCD_PG_Mimic_Driver,
    FCD_PG_Kinematic_Props, FCD_PG_AI_Props, FCD_PG_Lighting_Props, FCD_PG_Asset_Props,
    FCD_PG_Dimension_Props, FCD_ExportItem
]

def register():
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"Warning: FCD could not register {cls.__name__}: {e}")
    
    # Pointers
    bpy.types.Object.fcd_pg_mech_props = bpy.props.PointerProperty(type=FCD_PG_Mech_Props)
    bpy.types.PoseBone.fcd_pg_kinematic_props = bpy.props.PointerProperty(type=FCD_PG_Kinematic_Props)
    # Scene
    bpy.types.Scene.fcd_pg_ai_props = bpy.props.PointerProperty(type=FCD_PG_AI_Props)
    bpy.types.Scene.fcd_pg_lighting_props = bpy.props.PointerProperty(type=FCD_PG_Lighting_Props)
    bpy.types.Scene.fcd_pg_asset_props = bpy.props.PointerProperty(type=FCD_PG_Asset_Props)
    bpy.types.Scene.fcd_pg_joint_editor_settings = bpy.props.PointerProperty(type=FCD_PG_Kinematic_Props)
    bpy.types.Object.fcd_pg_dim_props = bpy.props.PointerProperty(type=FCD_PG_Dimension_Props)
    
    # Precision Scale State
    bpy.types.Scene.fcd_scale_axes = bpy.props.BoolVectorProperty(name="Scale Axes", size=3, default=(True, True, True))
    bpy.types.Scene.fcd_scale_value = bpy.props.FloatProperty(name="Value", default=1.0, subtype='DISTANCE')
    
    # UI Visibility (Initialize/Reset)
    from .config import FCD_PANEL_PROPS, MECH_CATEGORIES_SORTED, ELECTRONICS_CATEGORIES, ALL_ELECTRONICS_TYPES, ARCHITECTURAL_TYPES, VEHICLE_TYPES, GIZMO_STYLES, BONE_MODES, BONE_AXES
    
    # 1. Selection & Utility Properties
    bpy.types.Scene.fcd_part_category = bpy.props.EnumProperty(name="Category", items=MECH_CATEGORIES_SORTED)
    
    def fcd_part_type_items(self, context):
        cat = getattr(self, "fcd_part_category", 'GEAR')
        if cat == 'GEAR': return GEAR_TYPES
        elif cat == 'RACK': return RACK_TYPES
        elif cat == 'FASTENER': return FASTENER_TYPES
        elif cat == 'SPRING': return SPRING_TYPES
        elif cat == 'CHAIN': return CHAIN_TYPES
        elif cat == 'WHEEL': return WHEEL_TYPES
        elif cat == 'PULLEY': return PULLEY_TYPES
        elif cat == 'ROPE': return ROPE_TYPES
        elif cat == 'BASIC_JOINT': return BASIC_JOINT_TYPES
        elif cat == 'BASIC_SHAPE': return BASIC_SHAPE_TYPES
        elif cat == 'ARCHITECTURAL': return ARCHITECTURAL_TYPES
        elif cat == 'VEHICLE': return VEHICLE_TYPES
        return [('NONE', "None", "")]

    bpy.types.Scene.fcd_part_type = bpy.props.EnumProperty(name="Type", items=fcd_part_type_items)
    bpy.types.Scene.fcd_electronics_category = bpy.props.EnumProperty(name="Category", items=ELECTRONICS_CATEGORIES)
    bpy.types.Scene.fcd_electronics_type = bpy.props.EnumProperty(name="Type", items=ALL_ELECTRONICS_TYPES)
    bpy.types.Scene.fcd_architectural_type = bpy.props.EnumProperty(name="Type", items=ARCHITECTURAL_TYPES)
    bpy.types.Scene.fcd_vehicle_type = bpy.props.EnumProperty(name="Type", items=VEHICLE_TYPES)
    
    bpy.types.Scene.fcd_use_generation_cage = bpy.props.BoolProperty(name="Use Size Cage", default=False)
    bpy.types.Scene.fcd_generation_cage_size = bpy.props.FloatProperty(name="Max Dimension", default=0.2, unit='LENGTH')
    
    bpy.types.Scene.fcd_viz_gizmos = bpy.props.BoolProperty(name="Show Gizmos", default=True)
    bpy.types.Scene.fcd_show_bones = bpy.props.BoolProperty(name="Show Bones", default=True)
    bpy.types.Scene.fcd_auto_collapse_panels = bpy.props.BoolProperty(name="Auto-Collapse", default=True)
    bpy.types.Scene.fcd_text_placement_mode = bpy.props.BoolProperty(name="Text Placement", default=False)
    bpy.types.Scene.fcd_placement_mode = bpy.props.BoolProperty(name="Object Placement", default=False, update=update_placement_mode_wrapper)
    
    bpy.types.Scene.fcd_gizmo_style = bpy.props.EnumProperty(name="Style", items=GIZMO_STYLES, default='DEFAULT')
    bpy.types.Scene.fcd_bone_mode = bpy.props.EnumProperty(name="Mode", items=BONE_MODES, default='INDIVIDUAL')
    bpy.types.Scene.fcd_bone_axis = bpy.props.EnumProperty(name="Axis", items=BONE_AXES, default='AUTO')
    bpy.types.Scene.fcd_cursor_local_pos = bpy.props.FloatVectorProperty(name="Local Pos", size=3, unit='LENGTH', update=update_cursor_local_wrapper)
    bpy.types.Scene.fcd_active_rig = bpy.props.PointerProperty(type=bpy.types.Object, name="Active Rig")
    
    bpy.types.Scene.fcd_camera_preset = bpy.props.EnumProperty(
        name="Camera Preset",
        items=[
            ('35MM', "35mm Standard", "Standard full-frame lens"),
            ('70MM', "70mm Telephoto", "Longer lens for cinematic depth"),
            ('16MM', "16mm Ultra-Wide", "Action camera style (GoPro)"),
            ('8MM', "8mm Security", "Wide surveillance lens"),
        ],
        default='35MM'
    )
    
    # 1.1 Dimension Globals (FCD Scoped)
    bpy.types.Scene.fcd_dim_arrow_scale = bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.01)
    bpy.types.Scene.fcd_dim_text_scale = bpy.props.FloatProperty(name="Text Scale", default=0.1, min=0.01)
    bpy.types.Scene.fcd_dim_line_thickness = bpy.props.FloatProperty(name="Line Thickness", default=0.002, min=0.0, unit='LENGTH')
    bpy.types.Scene.fcd_dim_offset = bpy.props.FloatProperty(name="Offset", default=0.1, min=0.0, unit='LENGTH')
    bpy.types.Scene.fcd_dim_auto_scale_on_spawn = bpy.props.BoolProperty(name="Auto Scale Components", default=True)
    bpy.types.Scene.fcd_dim_axis = bpy.props.EnumProperty(
        name="Measurement Axis", 
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('ALL', "All Axes", "")], 
        default='ALL'
    )
    
    # 2. Export List
    bpy.types.Scene.fcd_export_list = bpy.props.CollectionProperty(type=FCD_ExportItem)
    bpy.types.Scene.fcd_export_list_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.fcd_export_check_meshes = bpy.props.BoolProperty(name="Meshes", default=True)
    bpy.types.Scene.fcd_export_check_textures = bpy.props.BoolProperty(name="Textures", default=True)
    bpy.types.Scene.fcd_export_check_config = bpy.props.BoolProperty(name="Config/URDF", default=True)
    bpy.types.Scene.fcd_export_check_launch = bpy.props.BoolProperty(name="Launch Files", default=True)
    bpy.types.Scene.fcd_export_mesh_format = bpy.props.EnumProperty(name="Format", items=[('STL', "STL", ""), ('DAE', "DAE", ""), ('OBJ', "OBJ", "")], default='STL')
    bpy.types.Scene.fcd_quick_export_format = bpy.props.EnumProperty(name="Quick Format", items=[('STL', "STL", ""), ('DAE', "DAE", ""), ('OBJ', "OBJ", "")], default='STL')
    
    # 3. Material Properties
    bpy.types.Scene.fcd_smart_material_type = bpy.props.EnumProperty(
        name="Material Type",
        items=[
            ('PLASTIC', "Plastic", ""),
            ('METAL', "Metal", ""),
            ('RUBBER', "Rubber", ""),
            ('EMISSIVE', "Emissive", ""),
            ('GLASS', "Glass", ""),
            ('CARBON', "Carbon Fiber", ""),
            ('PRINTED', "3D Printed", ""),
            ('ALUMINUM', "Brushed Aluminum", ""),
        ],
        default='PLASTIC'
    )
    
    def update_material_alpha(self, context):
        """Update active material alpha and trigger composite refresh."""
        obj = context.active_object
        if obj and obj.active_material:
            mat = obj.active_material
            if mat.use_nodes and mat.node_tree:
                bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if bsdf:
                    # Update the shader alpha value
                    bsdf.inputs['Alpha'].default_value = self.fcd_material_transparency
                    
                    # AI Editor Note: Removed automatic blend_method = 'BLEND' to support 
                    # non-destructive layering. This allows alpha to control the mix 
                    # factor in the Composite material without making the whole object 
                    # transparent to the world background.
                    
                    # Trigger a background re-merge to update the composite preview
                    from . import operators
                    operators.update_material_merge_trigger(self, context)
    def update_tex_transform(self, context):
        """Update active material mapping nodes instantly."""
        from . import core
        obj = context.active_object
        if obj and obj.active_material:
            core.ensure_material_mapping_nodes(obj.active_material)
            mat = obj.active_material
            mapping = next((n for n in mat.node_tree.nodes if n.type == 'MAPPING'), None)
            if mapping:
                mapping.inputs['Location'].default_value = self.fcd_tex_pos
                mapping.inputs['Rotation'].default_value = (0, 0, self.fcd_tex_rot)
                mapping.inputs['Scale'].default_value = self.fcd_tex_scale

    bpy.types.Scene.fcd_tex_pos = bpy.props.FloatVectorProperty(name="Position", size=3, update=update_tex_transform)
    bpy.types.Scene.fcd_tex_rot = bpy.props.FloatProperty(name="Rotation", update=update_tex_transform)
    bpy.types.Scene.fcd_tex_scale = bpy.props.FloatVectorProperty(name="Scale", size=3, default=(1.0, 1.0, 1.0), update=update_tex_transform)

    bpy.types.Scene.fcd_material_transparency = bpy.props.FloatProperty(
        name="Transparency",
        default=1.0,
        min=0.0,
        max=1.0,
        update=update_material_alpha
    )
    
    bpy.types.Scene.fcd_hook_placement_mode = bpy.props.BoolProperty(name="Hook Placement", default=False)
    
    # 3. Order Properties
    prop_names = [
        "fcd_order_ai_factory",    # 1: Generate
        "fcd_order_assets",        # 2: Asset Library
        "fcd_order_parts",         # 3: Mechanical Presets
        "fcd_order_electronics",   # 4: Electronic Presets
        "fcd_order_architectural", # 5: Architectural Presets
        "fcd_order_vehicle",       # 6: Vehicle Presets
        "fcd_order_procedural",    # 7: Procedural Toolkit
        "fcd_order_dimensions",    # 8: Dimensions & Measuring
        "fcd_order_kinematics",    # 9: Kinematics Setup
        "fcd_order_inertial",      # 10: Inertial
        "fcd_order_collision",     # 11: Collision
        "fcd_order_transmission",  # 12: Transmission
        "fcd_order_materials",     # 13: Materials & Textures
        "fcd_order_lighting",      # 14: Environment & Lighting
        "fcd_order_camera",        # 15: Camera Studio & Pathing
        "fcd_order_export",        # 16: Export System
        "fcd_order_preferences"    # 17: Preferences
    ]
    for i, name in enumerate(prop_names):
        setattr(bpy.types.Scene, name, bpy.props.IntProperty(name="Panel Order", default=i))

    # 4. Expansion Toggles
    for prop in FCD_PANEL_PROPS:
        try:
            if hasattr(bpy.types.Scene, prop):
                delattr(bpy.types.Scene, prop)
            
            # Start with all panels ENABLED (visible in list) but COLLAPSED (closed)
            is_show_prop = "show" in prop
            default_val = False if is_show_prop else True
            setattr(bpy.types.Scene, prop, bpy.props.BoolProperty(default=default_val))
        except Exception:
            pass

def unregister():
    """Systematic cleanup of all FCD properties and classes."""
    try:
        # 1. Clean up Scene Properties
        from .config import FCD_PANEL_PROPS
        all_scene_props = FCD_PANEL_PROPS + [
            "fcd_pg_ai_props", "fcd_pg_lighting_props", "fcd_pg_asset_props", "fcd_export_list",
            "fcd_pg_joint_editor_settings",
            "fcd_active_rig", "fcd_viz_gizmos", "fcd_show_bones", "fcd_auto_collapse_panels",
            "fcd_text_placement_mode", "fcd_placement_mode", "fcd_part_category", "fcd_part_type",
            "fcd_electronics_category", "fcd_electronics_type", "fcd_architectural_type", "fcd_vehicle_type",
            "fcd_use_generation_cage", "fcd_generation_cage_size", "fcd_gizmo_style", "fcd_bone_mode",
            "fcd_scale_axes", "fcd_scale_value",
            "fcd_bone_axis", "fcd_cursor_local_pos", "fcd_export_list_index", "fcd_export_check_meshes",
            "fcd_export_check_textures", "fcd_export_check_config", "fcd_export_check_launch",
            "fcd_export_mesh_format", "fcd_quick_export_format",
            "fcd_smart_material_type", "fcd_material_transparency",
            "fcd_tex_pos", "fcd_tex_rot", "fcd_tex_scale",
            "fcd_hook_placement_mode", "fcd_camera_preset"
        ]
        # Add order props
        prop_names = [
            "fcd_order_ai_factory", "fcd_order_parts", "fcd_order_architectural", "fcd_order_vehicle",
            "fcd_order_electronics", "fcd_order_procedural", "fcd_order_dimensions", "fcd_order_materials",
            "fcd_order_lighting", "fcd_order_kinematics", "fcd_order_inertial", "fcd_order_collision",
            "fcd_order_transmission", "fcd_order_assets", "fcd_order_export", "fcd_order_preferences"
        ]
        all_scene_props += prop_names
        
        for prop in all_scene_props:
            if hasattr(bpy.types.Scene, prop):
                delattr(bpy.types.Scene, prop)
        
        # 2. Clean up Object and Bone Pointers
        if hasattr(bpy.types.Object, "fcd_pg_mech_props"):
            del bpy.types.Object.fcd_pg_mech_props
        if hasattr(bpy.types.PoseBone, "fcd_pg_kinematic_props"):
            del bpy.types.PoseBone.fcd_pg_kinematic_props
            
    except Exception as e:
        print(f"Error during FCD property cleanup: {e}")
        
    # 3. Unregister classes in reverse order
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
