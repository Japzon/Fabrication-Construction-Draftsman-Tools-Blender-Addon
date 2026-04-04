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
from .. import config
from ..config import *
from .. import core
from .. import properties
from .. import operators
from . import ui_common

class LSD_PT_Mechanical_Presets:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Mechanical Presets' panel. It is not a
    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @staticmethod
    def draw_wheel_properties(context, layout, props):
        # --- Wheel Base Section (Common to all wheels) ---
        base_box = layout.box()
        base_box.label(text="Wheel Base", icon='MESH_CYLINDER')
        base_box.prop(props, "wheel_radius")
        base_box.prop(props, "wheel_width")

        # --- AI Editor Note: Segregated properties into clear sections for each wheel type ---
        if props.type_wheel == 'WHEEL_STANDARD':
            rim_box = layout.box()
            rim_box.label(text="Rim / Hub", icon='MESH_TORUS')
            rim_box.prop(props, "wheel_hub_radius", text="Radius")
            rim_box.prop(props, "wheel_hub_length", text="Width")
            rim_box.prop(props, "wheel_side_pattern", text="Side Pattern")
            
            tread_box = layout.box()
            tread_box.label(text="Tire Tread", icon='MOD_DISPLACE')
            tread_box.prop(props, "wheel_tread_pattern", text="Pattern")
            if props.wheel_tread_pattern == 'LINES':
                tread_box.prop(props, "wheel_tread_count")
        
        elif props.type_wheel == 'WHEEL_OFFROAD':
            sub_box = layout.box()
            sub_box.label(text="Treads", icon='MOD_DISPLACE')
            sub_box.prop(props, "wheel_tread_count")
            sub_box.prop(props, "wheel_sub_radius", text="Height")

        elif props.type_wheel == 'WHEEL_MECANUM':
            sub_box = layout.box()
            sub_box.label(text="Rollers", icon='MOD_ARRAY')
            sub_box.prop(props, "wheel_tread_count")
            sub_box.prop(props, "wheel_sub_radius", text="Radius")
            sub_box.prop(props, "wheel_sub_length", text="Length")
            sub_box.prop(props, "wheel_sub_support_thickness", text="Support Thickness")

        elif props.type_wheel == 'WHEEL_OMNI':
            sub_box = layout.box()
            sub_box.label(text="Rollers", icon='MOD_ARRAY')
            sub_box.prop(props, "wheel_tread_count")
            sub_box.prop(props, "wheel_sub_arrays", text="Arrays")
            sub_box.prop(props, "wheel_sub_radius", text="Radius")
            sub_box.prop(props, "wheel_sub_length", text="Length")
            sub_box.prop(props, "wheel_sub_support_thickness", text="Support Thickness")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # This panel is only drawn if its corresponding visibility toggle is enabled.
        return getattr(context.scene, "lsd_panel_enabled_parts", True)

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        """
        Main drawing logic for the Mechanical Presets panel.
        """
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Mechanical Presets", 
            "lsd_show_panel_parts", 
            "lsd_panel_enabled_parts"
        )
        
        if is_expanded:
            # --- NEW: Generation Size Constraint ---
            # This allows the user to define a bounding box to scale newly created parts.
            cage_box = box.box()
            cage_box.label(text="Generation Size Constraint", icon='SHADING_BBOX')
            cage_box.prop(scene, "lsd_use_generation_cage")
            row = cage_box.row()
            row.enabled = scene.lsd_use_generation_cage
            row.prop(scene, "lsd_generation_cage_size")

            row = box.row(align=True)
            row.prop(scene, "lsd_part_category", text="")
            row.prop(scene, "lsd_part_type", text="")
            r2 = box.row()
            r2.operator("lsd.create_part", text="Generate", icon='ADD')
            
            obj = context.active_object
            if obj and hasattr(obj, "lsd_pg_mech_props") and obj.lsd_pg_mech_props.is_part:
                box.separator()
                edit_box = box.box()

                # The 'props' are on the active object (e.g., the chain proxy).
                props = obj.lsd_pg_mech_props
                
                # --- UI CLEANUP: Display a clear, specific title for the part being edited. ---
                title = f"Edit {props.category.capitalize()}"
                if props.category == 'CHAIN':
                    title = f"Edit {props.type_chain.capitalize()}"
                elif props.category == 'RACK':
                    title = f"Edit {props.type_rack.replace('RACK_', '').title()} Rack"
                elif props.category == 'WHEEL':
                    # Clean up title for wheels
                    t_name = props.type_wheel.replace('WHEEL_', '').title()
                    title = f"Edit {t_name} Wheel"
                elif props.category == 'PULLEY':
                    t_name = props.type_pulley.replace('PULLEY_', '').title()
                    title = f"Edit {t_name}"
                elif props.category == 'ROPE':
                    t_name = props.type_rope.replace('ROPE_', '').title()
                    title = f"Edit {t_name}"
                elif props.category == 'BASIC_JOINT':
                    t_name = props.type_basic_joint.replace('JOINT_', '').title()
                    title = f"Edit {t_name}"
                elif props.category == 'BASIC_SHAPE':
                    t_name = props.type_basic_shape.replace('SHAPE_', '').title()
                    title = f"Edit {t_name}"

                edit_box.label(text=title, icon='MODIFIER')

                if props.category == 'GEAR':
                    edit_box.prop(props, "gear_radius")
                    edit_box.prop(props, "gear_width")
                    if props.type_gear == 'INTERNAL':
                        edit_box.prop(props, "gear_outer_radius")
                    
                    # --- AI Editor Note: Teeth Properties Below ---
                    edit_box.separator()
                    edit_box.label(text="Teeth Parameters")
                    edit_box.prop(props, "gear_teeth_count")
                    edit_box.prop(props, "tooth_spacing")
                    edit_box.prop(props, "gear_tooth_depth")
                    edit_box.prop(props, "gear_tooth_taper")
                    
                    if props.type_gear not in ['SPUR']:
                        if props.type_gear in ['BEVEL']:
                            edit_box.prop(props, "twist", text="Bevel Angle")
                        else:
                            edit_box.prop(props, "twist", text="Twist Angle")
                    if props.type_gear != 'INTERNAL':
                        b_box = edit_box.box()
                        b_box.label(text="Shaft Bore")
                        b_box.prop(props, "bore_radius")
                        if props.bore_radius > 0:
                            b_box.prop(props, "bore_type")
                elif props.category == 'RACK':
                    edit_box.prop(props, "rack_width")
                    edit_box.prop(props, "rack_length")
                    edit_box.prop(props, "rack_height")
                    
                    edit_box.separator()
                    edit_box.label(text="Teeth Parameters")
                    edit_box.prop(props, "rack_teeth_count")
                    edit_box.prop(props, "tooth_spacing")
                    edit_box.prop(props, "rack_tooth_depth")
                    edit_box.prop(props, "gear_tooth_taper")
                    
                    if props.type_rack not in ['RACK_SPUR']:
                        if props.type_rack in ['RACK_BEVEL']:
                            edit_box.prop(props, "twist", text="Bevel Angle")
                        else:
                            edit_box.prop(props, "twist", text="Twist Angle")
                elif props.category == 'FASTENER': 
                    edit_box.prop(props, "fastener_radius")
                    edit_box.prop(props, "fastener_length")
                elif props.category == 'SPRING': 
                    edit_box.prop(props, "type_spring", text="Type")
                    if props.type_spring == 'SPRING':
                        edit_box.prop(props, "spring_radius")
                        edit_box.prop(props, "spring_wire_thickness")
                        edit_box.prop(props, "spring_turns")
                    elif props.type_spring == 'DAMPER':
                        edit_box.prop(props, "spring_radius")
                        edit_box.prop(props, "spring_wire_thickness")
                        edit_box.prop(props, "spring_turns")
                        edit_box.separator()
                        edit_box.prop(props, "gear_outer_radius", text="Housing Radius")
                        edit_box.prop(props, "gear_bore_radius", text="Rod Radius")
                        edit_box.prop(props, "joint_width", text="Housing/Rod Length")
                        edit_box.prop(props, "damper_seat_radius", text="Seat Radius")
                        edit_box.prop(props, "damper_seat_thickness", text="Seat Thickness")
                    elif props.type_spring == 'SPRING_SLINKY':
                        edit_box.prop(props, "spring_radius")
                        edit_box.prop(props, "spring_wire_thickness")
                        edit_box.prop(props, "spring_turns")
                        
                        hook_box = edit_box.box()
                        hook_box.label(text="Path Hooks (Middle)", icon='HOOK')
                        row = hook_box.row()
                        row.template_list("LSD_UL_SlinkyHooks_List", "slinky_hooks", props, "slinky_hooks", props, "slinky_active_index")
                        
                        col = row.column(align=True)
                        col.operator("lsd.slinky_add_hook", icon='ADD', text="")
                        col.operator("lsd.slinky_remove_hook", icon='REMOVE', text="")
                    # The 'length' property is hidden as it is dynamically controlled
                    # by the distance between the start and end helper objects.
                elif props.category == 'CHAIN':
                    # The type_chain property is now immutable from the UI after creation.
                    edit_box.prop(props, "chain_pitch")
                    
                    if props.type_chain == 'ROLLER':
                        edit_box.prop(props, "chain_roller_radius")
                        edit_box.prop(props, "chain_roller_length")
                        edit_box.prop(props, "chain_plate_height")
                        edit_box.prop(props, "chain_plate_thickness")
                    elif props.type_chain == 'BELT':
                        edit_box.prop(props, "belt_width")
                        edit_box.prop(props, "belt_thickness")

                    # --- NEW: Animation Control ---
                    anim_box = edit_box.box()
                    anim_box.label(text="Drive System", icon='DRIVER')
                    row = anim_box.row(align=True)
                    row.prop(props, "chain_drive_target", text="")
                    row.operator("lsd.link_chain_driver", text="Update Driver", icon='FILE_REFRESH')
                    
                    # --- AI Editor Note: Manual Drive Controls ---
                    row = anim_box.row(align=True)
                    row.prop(props, "chain_drive_ratio", text="Ratio")
                    row.prop(props, "chain_drive_invert", text="Invert", toggle=True)

                    # --- Dynamic Wrapping (Convex Hull) ---
                    # This section allows the user to add objects to a collection.
                    # The chain path is then generated from the convex hull of these objects.
                    wrap_box = edit_box.box()
                    wrap_box.label(text="Dynamic Wrapping (Bundle)", icon='MOD_SHRINKWRAP')
                    
                    # NEW: Picker UI for easier selection
                    row = wrap_box.row(align=True)
                    row.prop(props, "wrap_picker")
                    row.operator("lsd.chain_add_picked_wrap_object", text="", icon='ADD')
                    
                    # Legacy operator for selection-based adding
                    wrap_box.operator("lsd.chain_add_wrap_object", icon='SELECT_SET', text="Add Selected Objects")
                    
                    # This UIList displays the collection of hooks.
                    wrap_box.template_list(
                        "UI_UL_WrapItems", "", props, "chain_wrap_items", 
                        props, "chain_active_index"
                    )
                elif props.category == 'WHEEL':
                    # --- Wheel Base Section (Common to all wheels) ---
                    base_box = edit_box.box()
                    base_box.label(text="Wheel Base", icon='MESH_CYLINDER')
                    base_box.prop(props, "wheel_radius")
                    base_box.prop(props, "wheel_width")

                    # --- AI Editor Note: Segregated properties into clear sections for each wheel type ---
                    if props.type_wheel == 'WHEEL_STANDARD':
                        rim_box = edit_box.box()
                        rim_box.label(text="Rim / Hub", icon='MESH_TORUS')
                        rim_box.prop(props, "wheel_hub_radius", text="Radius")
                        rim_box.prop(props, "wheel_hub_length", text="Width")
                        rim_box.prop(props, "wheel_side_pattern", text="Side Pattern")
                        
                        if props.wheel_side_pattern != 'NONE':
                            rim_box.prop(props, "wheel_pattern_spacing", text="Spacing")
                            rim_box.prop(props, "wheel_pattern_depth", text="Depth")
                        
                        tread_box = edit_box.box()
                        tread_box.label(text="Tire Tread", icon='MOD_DISPLACE')
                        tread_box.prop(props, "wheel_tread_pattern", text="Pattern")
                        if props.wheel_tread_pattern == 'LINES':
                            tread_box.prop(props, "wheel_tread_count")
                        
                        # AI Editor Note: Expose pattern properties for treads as requested
                        if props.wheel_tread_pattern != 'NONE':
                            tread_box.prop(props, "wheel_pattern_spacing", text="Spacing")
                            tread_box.prop(props, "wheel_pattern_depth", text="Depth")
                    
                    elif props.type_wheel == 'WHEEL_OFFROAD':
                        sub_box = edit_box.box()
                        sub_box.label(text="Treads", icon='MOD_DISPLACE')
                        sub_box.prop(props, "wheel_tread_count")
                        sub_box.prop(props, "wheel_sub_radius", text="Height")

                    elif props.type_wheel == 'WHEEL_MECANUM':
                        sub_box = edit_box.box()
                        sub_box.label(text="Rollers", icon='MOD_ARRAY')
                        sub_box.prop(props, "wheel_tread_count")
                        sub_box.prop(props, "wheel_sub_radius", text="Radius")
                        sub_box.prop(props, "wheel_sub_length", text="Length")
                        sub_box.prop(props, "wheel_sub_support_thickness", text="Support Thickness")

                    elif props.type_wheel == 'WHEEL_OMNI':
                        sub_box = edit_box.box()
                        sub_box.label(text="Rollers", icon='MOD_ARRAY')
                        sub_box.prop(props, "wheel_tread_count")
                        sub_box.prop(props, "wheel_sub_arrays", text="Arrays")
                        sub_box.prop(props, "wheel_sub_radius", text="Radius")
                        sub_box.prop(props, "wheel_sub_length", text="Length")
                        sub_box.prop(props, "wheel_sub_support_thickness", text="Support Thickness")
                        sub_box.prop(props, "wheel_sub_support_length", text="Support Length")

                elif props.category == 'PULLEY':
                    edit_box.prop(props, "pulley_radius")
                    edit_box.prop(props, "pulley_width")
                    edit_box.prop(props, "pulley_groove_depth")
                    if props.type_pulley == 'PULLEY_TIMING':
                        edit_box.prop(props, "pulley_teeth_count")
                elif props.category == 'ROPE':
                    edit_box.prop(props, "rope_radius")
                    edit_box.prop(props, "rope_length")
                    if props.type_rope in ['ROPE_STEEL', 'ROPE_SYNTHETIC']:
                        edit_box.prop(props, "rope_strands")
                        edit_box.prop(props, "twist", text="Twist Rate")
                    elif props.type_rope == 'ROPE_TUBE':
                        pass # Wall Thickness removed per user request
                elif props.category == 'BASIC_JOINT':
                    if props.type_basic_joint == 'JOINT_REVOLUTE':
                        # AI Editor Note: Reorganized properties into logical groups for clarity.
                        # Stator properties
                        stator_box = edit_box.box()
                        stator_box.label(text="Stator (Frame)", icon='MESH_CUBE')
                        stator_box.prop(props, "joint_width", text="Joint Width")
                        stator_box.prop(props, "joint_sub_thickness", text="Frame Thickness")
                        stator_box.prop(props, "joint_frame_width", text="Frame Width")
                        stator_box.prop(props, "joint_frame_length", text="Frame Length")

                        # Rotor properties
                        rotor_box = edit_box.box()
                        rotor_box.label(text="Rotor (Moving Part)", icon='MESH_CYLINDER')
                        rotor_box.prop(props, "joint_radius", text="Eye Radius")
                        rotor_box.prop(props, "rotor_arm_length")
                        rotor_box.prop(props, "rotor_arm_width")
                        rotor_box.prop(props, "rotor_arm_height")

                        # Pin properties
                        pin_box = edit_box.box()
                        # AI Editor Note: The 'PIN' icon was removed in recent Blender versions.
                        pin_box.label(text="Pin", icon='GRIP')
                        pin_box.prop(props, "joint_pin_radius", text="Pin Radius")
                        pin_box.prop(props, "joint_sub_size", text="Pin Overhang")
                    elif props.type_basic_joint == 'JOINT_CONTINUOUS':
                        edit_box.prop(props, "joint_base_radius")
                        edit_box.prop(props, "joint_base_length")
                        edit_box.prop(props, "joint_motor_shaft_radius")
                        edit_box.prop(props, "joint_motor_shaft_length")
                    elif props.type_basic_joint == 'JOINT_PRISMATIC':
                        edit_box.prop(props, "joint_width", text="Screw Length")
                        edit_box.prop(props, "joint_radius", text="Screw Radius")
                        edit_box.prop(props, "joint_sub_size", text="Nut Block Size")
                    elif props.type_basic_joint == 'JOINT_PRISMATIC_WHEELS':
                        # AI Editor Note: Updated UI layout per user request.
                        # 1. Rack Thickness (using 'length')
                        # 2. Rack Length (using new 'rack_length')
                        # 3. Wheel Radius
                        # 4. Wheel Thickness
                        # 5. Axle Length
                        # 6. Carriage Length
                        # 7. Carriage Width
                        # 8. Carriage Thickness
                        edit_box.prop(props, "joint_sub_thickness", text="Rack Thickness")
                        edit_box.prop(props, "rack_length", text="Rack Length")
                        edit_box.prop(props, "rack_width", text="Rack Width")
                        edit_box.prop(props, "joint_radius", text="Wheel Radius")
                        edit_box.prop(props, "wheel_thickness")
                        edit_box.prop(props, "wheel_axle_length")
                        edit_box.prop(props, "joint_sub_size", text="Carriage Length")
                        edit_box.prop(props, "joint_carriage_width")
                        edit_box.prop(props, "joint_carriage_thickness")
                        # AI Editor Note: Removed duplicate properties that were here previously.
                    elif props.type_basic_joint == 'JOINT_PRISMATIC_WHEELS_ROT':
                        edit_box.prop(props, "rack_length", text="Rack Length")
                        edit_box.prop(props, "rack_width", text="Rack Width")
                        edit_box.prop(props, "joint_sub_thickness", text="Rack Thickness")
                        edit_box.prop(props, "joint_radius", text="Wheel Radius")
                        edit_box.prop(props, "wheel_thickness")
                        edit_box.prop(props, "joint_sub_size", text="Carriage Length")
                        edit_box.prop(props, "joint_carriage_width")
                        edit_box.prop(props, "joint_carriage_thickness")
                    elif props.type_basic_joint == 'JOINT_SPHERICAL':
                        edit_box.prop(props, "joint_radius", text="Ball Radius")
                        edit_box.prop(props, "joint_sub_size", text="Housing Size")
                        edit_box.prop(props, "joint_sub_thickness", text="Socket Thickness")
                        edit_box.prop(props, "joint_pin_radius", text="Stem Radius")
                        edit_box.prop(props, "joint_pin_length", text="Stem Length")
                elif props.category == 'BASIC_SHAPE':
                    if props.type_basic_shape == 'SHAPE_PLANE':
                        edit_box.prop(props, "shape_size")
                    elif props.type_basic_shape == 'SHAPE_CUBE':
                        edit_box.prop(props, "shape_length_x")
                        edit_box.prop(props, "shape_width_y")
                        edit_box.prop(props, "shape_height_z")
                    elif props.type_basic_shape == 'SHAPE_CIRCLE':
                        edit_box.prop(props, "shape_radius")
                        edit_box.prop(props, "shape_vertices")
                    elif props.type_basic_shape == 'SHAPE_CYLINDER':
                        edit_box.prop(props, "shape_radius")
                        edit_box.prop(props, "shape_height")
                        edit_box.prop(props, "shape_vertices")
                    elif props.type_basic_shape == 'SHAPE_UVSPHERE':
                        edit_box.prop(props, "shape_radius")
                        edit_box.prop(props, "shape_segments")
                    elif props.type_basic_shape == 'SHAPE_ICOSPHERE':
                        edit_box.prop(props, "shape_radius")
                        edit_box.prop(props, "shape_subdivisions")
                    elif props.type_basic_shape == 'SHAPE_CONE':
                        edit_box.prop(props, "shape_radius")
                        edit_box.prop(props, "shape_height")
                        edit_box.prop(props, "shape_vertices")
                    elif props.type_basic_shape == 'SHAPE_TORUS':
                        edit_box.prop(props, "shape_major_radius")
                        edit_box.prop(props, "shape_tube_radius")
                        edit_box.prop(props, "shape_horizontal_segments")
                        edit_box.prop(props, "shape_vertical_segments")
                
                # This button applies to all parametric part types
                edit_box.separator()
                # DEBUG FIX: The Bake Mesh operator was missing from the UI. This restores it.
                edit_box.operator("lsd.bake_mesh", icon='CHECKMARK')

                # --- Material Properties (Kept here for context) ---
                material_box = edit_box.box()
                material_box.label(text="Material", icon='MATERIAL')
                material_box.prop(props.material, "color")
                material_box.prop(props.material, "texture")

# ------------------------------------------------------------------------
#   PANEL: MATERIALS & TEXTURING
#   Order: 4
#   Description: Streamlined material management (Photoshop-like layers)
# ------------------------------------------------------------------------

def register():
    for cls in [LSD_PT_Mechanical_Presets]:
        if hasattr(cls, 'bl_rna'):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass

def unregister():
    for cls in reversed([LSD_PT_Mechanical_Presets]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

