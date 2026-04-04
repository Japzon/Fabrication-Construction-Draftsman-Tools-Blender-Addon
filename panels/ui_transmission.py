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

class LSD_PT_Transmission:
    """
    AI Editor Note:
    This class is a drawing helper for the 'Transmission' panel. It is not a
    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanToolsAutomated
    to draw its content. This structure allows for dynamic reordering of panels.
    """

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # AI Editor Note: Panel is now always available if enabled in preferences.
        return context.scene.lsd_panel_enabled_transmission

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene
        
        # 1. Standardized Header
        box, is_expanded = ui_common.draw_panel_header(
            layout, context, 
            "Transmission", 
            "lsd_show_panel_transmission", 
            "lsd_panel_enabled_transmission"
        )
        
        if is_expanded:
            pb = context.active_pose_bone
            if pb:
                props = pb.lsd_pg_kinematic_props
                transmission_props = props.transmission
                box.prop(transmission_props, "type", text="Type")
                box.prop(transmission_props, "joint")
                box.prop(transmission_props, "hardware_interface")
                box.prop(transmission_props, "mechanical_reduction")
            else:
                box.label(text="Select a Pose Bone (Pose Mode)", icon='INFO')


def register():
    for cls in [LSD_PT_Transmission]:
        if hasattr(cls, 'bl_rna'):
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed([LSD_PT_Transmission]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

