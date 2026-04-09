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

class LSD_PT_Procedural_Toolkit:

    """

    AI Editor Note:

    This class is a drawing helper for the 'Procedural Toolkit' panel. It is not a

    registered bpy.types.Panel, but is called by the main LSD_PT_FabricationConstructionDraftsmanTools

    to draw its content. This structure allows for dynamic reordering of panels.

    """

    @classmethod

    def poll(cls, context: bpy.types.Context) -> bool:

        # This panel is only drawn if its corresponding visibility toggle is enabled.

        return context.scene.lsd_panel_enabled_procedural

    @staticmethod
    def draw(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
        scene = context.scene

        # --- Header ---
        box, is_expanded = ui_common.draw_panel_header(layout, context, "Procedural Toolkit", "lsd_show_panel_procedural", "lsd_panel_enabled_procedural")

        if is_expanded:
            col_main = box.column(align=True)

            # --- Dedicated Sub-Panel: Path Tools ---
            path_box = col_main.box()
            path_box.label(text="Path Tools", icon='CURVE_PATH')
            
            row = path_box.row(align=True)
            # 1. Spawn Vertex: Drafting tool for path and vertex generation
            row.operator_menu_enum("lsd.create_curve_for_path", "type", text="Spawn Vertex", icon='ADD')
            
            # --- Technical Note (Mechatronic Drafting) ---
            # 'Mesh Vertex' allows for high-precision vertex-instancing, while
            # 'Bezier/NURBS Path' provides flexible drafting for hoses and cables.

            row.operator_menu_enum("lsd.setup_curve_array", "mode", text="Follow Path", icon='HOOK')

            # --- Vertex Axis Alignments (Precision Snap) ---
            # These 6 buttons allow for batch-alignment of selected path vertices
            # to the global bounding box boundaries (+/- XYZ).
            align_box = path_box.box()
            align_box.label(text="Vertex Axis Alignments", icon='CURSOR')
            
            # 2x3 Grid of Alignment Targets (Manually implemented for compatibility)
            grid_col = align_box.column(align=True)
            row_pos = grid_col.row(align=True)
            row_pos.prop(scene, "lsd_path_align_pos", index=0, text="+X", toggle=True)
            row_pos.prop(scene, "lsd_path_align_pos", index=1, text="+Y", toggle=True)
            row_pos.prop(scene, "lsd_path_align_pos", index=2, text="+Z", toggle=True)
            
            row_neg = grid_col.row(align=True)
            row_neg.prop(scene, "lsd_path_align_neg", index=0, text="-X", toggle=True)
            row_neg.prop(scene, "lsd_path_align_neg", index=1, text="-Y", toggle=True)
            row_neg.prop(scene, "lsd_path_align_neg", index=2, text="-Z", toggle=True)


            # Live Calibration & Commit
            cal_row = align_box.row(align=True)
            cal_row.scale_y = 1.2
            
            # Calibration Toggle (Blue style as per reference)
            cal_row.prop(scene, "lsd_path_live_align", text="Live Calibration", toggle=True, icon='TIME')
            
            # Commit Alignment (Only useful if Live is on, or to clear the mask)
            if scene.lsd_path_live_align:
                cal_row.operator("lsd.commit_path_alignment", text="Commit Alignment", icon='CHECKMARK')

            # Note: Over-simplistic modifiers and cleanup tools have been removed




def register():

    for cls in [LSD_PT_Procedural_Toolkit]:

        if hasattr(cls, 'bl_rna'):

            bpy.utils.register_class(cls)

def unregister():

    for cls in reversed([LSD_PT_Procedural_Toolkit]):

        if hasattr(cls, 'bl_rna'):

            bpy.utils.unregister_class(cls)

