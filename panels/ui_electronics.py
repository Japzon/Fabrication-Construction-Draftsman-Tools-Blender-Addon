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

class URDF_PT_CreateElectronicComponents:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Create Electronic Components' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.urdf_panel_enabled_electronics

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        is_expanded = scene.urdf_show_panel_electronics
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Create Electronic Components", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_electronics"
        row.prop(scene, "urdf_show_panel_electronics", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_electronics"


        if is_expanded:
            cage_box = box.box()
            cage_box.label(text="Generation Size Constraint", icon='SHADING_BBOX')
            cage_box.prop(scene, "urdf_use_generation_cage")
            row = cage_box.row()
            row.enabled = scene.urdf_use_generation_cage
            row.prop(scene, "urdf_generation_cage_size")

            row = box.row(align=True)
            row.prop(scene, "urdf_electronics_category", text="")
            row.prop(scene, "urdf_electronics_type", text="")
            r2 = box.row()
            r2.operator("urdf.create_electronic_part", text="Generate", icon='ADD')
            
            obj = context.active_object
            if obj and hasattr(obj, "urdf_mech_props") and obj.urdf_mech_props.is_part and obj.urdf_mech_props.category == 'ELECTRONICS':
                box.separator()
                edit_box = box.box()
                props = obj.urdf_mech_props
                edit_box.label(text=f"Edit {props.type_electronics.replace('_', ' ').title()}", icon='MODIFIER')

                if 'MOTOR' in props.type_electronics:
                    col = edit_box.column(align=True)
                    col.label(text="Body Dimensions:")
                    if props.type_electronics in ['MOTOR_SERVO_STD', 'MOTOR_SERVO_MICRO']:
                        col.prop(props, "motor_length", text="Case Length")
                        col.prop(props, "motor_radius", text="Half Width")
                        col.prop(props, "motor_height", text="Case Height")
                    else:
                        col.prop(props, "motor_radius", text="Radius")
                        col.prop(props, "motor_length", text="Length")

                    edit_box.separator()
                    col = edit_box.column(align=True)
                    col.prop(props, "motor_shaft")
                    if props.motor_shaft:
                        sub = col.column(align=True)
                        sub.label(text="Shaft:")
                        sub.prop(props, "motor_shaft_radius", text="Radius")
                        sub.prop(props, "motor_shaft_length", text="Length")
                elif 'IC' in props.type_electronics:
                    edit_box.prop(props, "ic_width", text="Width")
                    edit_box.prop(props, "ic_length", text="Length")
                    edit_box.prop(props, "ic_height", text="Height")
                    if props.type_electronics == 'IC_MICROCHIP':
                        edit_box.prop(props, "ic_pin_count")
                elif 'CAMERA' in props.type_electronics or 'SENSOR' in props.type_electronics:
                    # Puck-like sensors
                    if props.type_electronics in ['SENSOR_LIDAR', 'SENSOR_FORCE_TORQUE']:
                        edit_box.prop(props, "sensor_radius")
                        edit_box.prop(props, "sensor_length", text="Thickness")
                    # Box-like sensors
                    elif 'CAMERA' in props.type_electronics:
                        edit_box.prop(props, "camera_case_length")
                        edit_box.prop(props, "camera_case_width")
                        edit_box.prop(props, "camera_case_height")
                        edit_box.prop(props, "camera_lens_radius")
                    else:
                        edit_box.prop(props, "sensor_length")
                        edit_box.prop(props, "sensor_radius", text="Width")
                        edit_box.prop(props, "sensor_height")

                    # Special properties for specific types
                    if props.type_electronics == 'SENSOR_ULTRASONIC':
                        edit_box.prop(props, "ic_pin_count", text="Transducers")
                elif 'PCB' in props.type_electronics:
                    edit_box.prop(props, "pcb_width", text="Width")
                    edit_box.prop(props, "pcb_length", text="Length")
                    edit_box.prop(props, "pcb_thickness", text="Thickness")
                    edit_box.prop(props, "pcb_hole_radius", text="Mounting Radius")
                else:
                    # Fallback for other electronics
                    edit_box.prop(props, "radius")
                    edit_box.prop(props, "length")
                
                edit_box.separator()
                edit_box.operator("urdf.bake_mesh", icon='CHECKMARK')

# ------------------------------------------------------------------------
#   PANEL: SOLID MODELING (PARAMETRIC)
#   Order: 3
#   Description: General purpose modeling tools (booleans, arrays, etc.)
# ------------------------------------------------------------------------

def register():
    for cls in [URDF_PT_CreateElectronicComponents]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_CreateElectronicComponents]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)
