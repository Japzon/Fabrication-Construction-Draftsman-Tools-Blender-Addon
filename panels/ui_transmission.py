# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
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

class URDF_PT_Transmission:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Transmission' panel. It is not a
    registered bpy.types.Panel, but is called by the main URDF_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # AI Editor Note: Panel is now always available if enabled in preferences.
        return context.scene.urdf_panel_enabled_transmission

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        box = layout.box()
        
        is_expanded = scene.urdf_show_panel_transmission
        icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
        row = box.row(align=True)
        op = row.operator("urdf.toggle_panel_visibility", text="Transmission", emboss=False, icon=icon)
        op.panel_property = "urdf_show_panel_transmission"
        row.prop(scene, "urdf_show_panel_transmission", text="", emboss=False, toggle=True)
        close_op = row.operator("urdf.disable_panel", text="", icon='X')
        close_op.prop_name = "urdf_panel_enabled_transmission"


        if is_expanded:
            pb = context.active_pose_bone
            if pb:
                props = pb.urdf_props
                transmission_props = props.transmission
                box.prop(transmission_props, "type", text="Type")
                box.prop(transmission_props, "joint")
                box.prop(transmission_props, "hardware_interface")
                box.prop(transmission_props, "mechanical_reduction")
            else:
                box.label(text="Select a Pose Bone (Pose Mode)", icon='INFO')


def register():
    for cls in [URDF_PT_Transmission]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([URDF_PT_Transmission]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

