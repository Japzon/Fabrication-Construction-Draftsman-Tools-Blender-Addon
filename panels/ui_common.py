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

def draw_panel_header(layout: bpy.types.UILayout, context: bpy.types.Context, title: str, show_prop: str, enabled_prop: str) -> Tuple[bpy.types.UILayout, bool]:
    """
    Draws a standardized triad toggle and close button for a panel header.
    Returns the box layout and the expanded state.
    """
    box = layout.box()
    row = box.row(align=True)
    scene = context.scene
    
    is_expanded = getattr(scene, show_prop, False)
    icon = 'TRIA_DOWN' if is_expanded else 'TRIA_RIGHT'
    
    # Toggle button for expansion
    op = row.operator("fcd.toggle_panel_visibility", text=title, icon=icon, emboss=False)
    op.panel_property = show_prop
    row.prop(scene, show_prop, text="", emboss=False, toggle=True)
    
    # Close button to disable panel entirely
    close_op = row.operator("fcd.disable_panel", text="", icon='X')
    close_op.prop_name = enabled_prop
    
    return box, is_expanded


class FCD_OT_UpdatePanelOrder(bpy.types.Operator):
    """Updates the order of panels in the UI based on the settings in Preferences"""
    bl_idname = "fcd.update_panel_order"
    bl_label = "Apply Panel Order"
    bl_description = "Updates the order of panels in the UI based on the settings above"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Force redraw of all 3D View UI regions to ensure the change is visible immediately
        # The actual sorting is now handled dynamically by FCD_PT_FabricationConstructionDraftsmanToolsAutomated
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D' or area.type == 'PREFERENCES':
                    area.tag_redraw()
        return {'FINISHED'}

class FCD_OT_ToggleTextPlacement(bpy.types.Operator):
    """Toggle placement mode for text labels. Unlocks dimensions for manual positioning."""
    bl_idname = "fcd.toggle_text_placement"
    bl_label = "Toggle Text Placement"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # AI Editor Note: Ensure Object Mode to prevent context errors during selection/parenting
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        scene = context.scene
        is_starting = not scene.fcd_text_placement_mode
        scene.fcd_text_placement_mode = is_starting
        
        coll = bpy.data.collections.get("FCD_Dimensions")
        if not coll:
            self.report({'WARNING'}, "No Dimensions collection found.")
            return {'FINISHED'}

        if is_starting:
            # Unlock Dimensions: Create anchors if they don't exist
            bpy.ops.object.select_all(action='DESELECT')
            
            for obj in coll.objects:
                # Handle Dimensions (Mesh with GN)
                if obj.get("fcd_is_dimension"):
                    # AI Editor Note: Capture current visual transform (including billboard rotation)
                    visual_matrix = obj.matrix_world.copy()

                    # Check if it's directly constrained (locked)
                    has_copy_loc = any(c.type == 'COPY_LOCATION' for c in obj.constraints)
                    
                    if has_copy_loc:
                        # Create Anchor Empty
                        anchor = bpy.data.objects.new(f"Anchor_{obj.name}", None)
                        anchor.location = obj.matrix_world.translation
                        anchor.empty_display_type = 'PLAIN_AXES'
                        anchor.empty_display_size = 0.1
                        coll.objects.link(anchor)
                        
                        # Move constraints to Anchor
                        # AI Editor Note: Iterate over a copy to avoid skipping items during removal
                        constraints_to_move = [c for c in obj.constraints if c.type == 'COPY_LOCATION']
                        for c in constraints_to_move:
                            new_c = anchor.constraints.new('COPY_LOCATION')
                            new_c.target = c.target
                            new_c.influence = c.influence
                            obj.constraints.remove(c)
                        
                        # AI Editor Note: Force update to ensure anchor position is valid before parenting
                        context.view_layer.update()
                        
                        # Parent Text to Anchor
                        obj.parent = anchor
                        # AI Editor Note: Reset local transform to identity to snap to anchor (midpoint).
                        # Setting matrix_world can cause drift if the anchor isn't fully evaluated.
                        obj.matrix_local = mathutils.Matrix.Identity(4)
                    
                    # AI Editor Note: Mute rotation constraints to allow manual rotation
                    for c in obj.constraints:
                        if c.type in {'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK', 'COPY_ROTATION'}:
                            c.mute = True

                    # AI Editor Note: Restore visual transform to prevent snapping/jumping
                    obj.matrix_world = visual_matrix

                    # Select for easy movement
                    # AI Editor Note: Mark as manually placed so it doesn't reset on arrow scale change.
                    # Set this unconditionally when entering placement mode to ensure state is saved.
                    obj.fcd_dim_is_manual = True
                    
                    obj.select_set(True)
                
                # Handle Text Descriptions (Font)
                elif obj.type == 'FONT':
                    # AI Editor Note: Mute rotation constraints
                    for c in obj.constraints:
                        if c.type in {'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK', 'COPY_ROTATION'}:
                            c.mute = True
                    obj.select_set(True)
            
            self.report({'INFO'}, "Text Placement Mode: Move/Rotate text objects freely.")
        else:
            # Stop Placement: Unmute constraints to restore behavior (e.g. billboarding)
            for obj in coll.objects:
                if obj.get("fcd_is_dimension") or obj.type == 'FONT':
                    # AI Editor Note: Removed manual location recalculation.
                    # The object is parented to the anchor, which is constrained to the midpoint.
                    # Any movement done by the user is stored in the object's local transform relative to the anchor.
                    # Recalculating it here was causing double-transforms and misplacement.
                    for c in obj.constraints:
                        if c.type in {'TRACK_TO', 'DAMPED_TRACK', 'LOCKED_TRACK', 'COPY_ROTATION'}:
                            c.mute = False

            bpy.ops.object.select_all(action='DESELECT')
            self.report({'INFO'}, "Text Placement Mode Stopped.")
            
        return {'FINISHED'}

class FCD_OT_MovePanel(bpy.types.Operator):
    """Move panel up or down in the list"""
    bl_idname = "fcd.move_panel"
    bl_label = "Move Panel"
    
    prop_name: bpy.props.StringProperty()
    direction: bpy.props.EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])
    
    def execute(self, context):
        scene = context.scene
        # Map of prop_name -> current_order
        props = {
            "fcd_order_ai_factory": scene.fcd_order_ai_factory,
            "fcd_order_parts": scene.fcd_order_parts,
            "fcd_order_architectural": scene.fcd_order_architectural,
            "fcd_order_vehicle": scene.fcd_order_vehicle,
            "fcd_order_electronics": scene.fcd_order_electronics,
            "fcd_order_procedural": scene.fcd_order_procedural,
            "fcd_order_dimensions": scene.fcd_order_dimensions,
            "fcd_order_materials": scene.fcd_order_materials,
            "fcd_order_lighting": scene.fcd_order_lighting,
            "fcd_order_camera": scene.fcd_order_camera,
            "fcd_order_kinematics": scene.fcd_order_kinematics,
            "fcd_order_physics": scene.fcd_order_physics,
            "fcd_order_transmission": scene.fcd_order_transmission,
            "fcd_order_assets": scene.fcd_order_assets,
            "fcd_order_export": scene.fcd_order_export,
            "fcd_order_preferences": scene.fcd_order_preferences,
        }
        
        # Sort by order to get the current sequence
        sorted_props = sorted(props.items(), key=lambda x: x[1])
        
        # Find current index of the panel we want to move
        try:
            idx = next(i for i, (name, _) in enumerate(sorted_props) if name == self.prop_name)
        except StopIteration:
            return {'CANCELLED'}
            
        # Swap with neighbor
        if self.direction == 'UP' and idx > 0:
            sorted_props[idx], sorted_props[idx-1] = sorted_props[idx-1], sorted_props[idx]
        elif self.direction == 'DOWN' and idx < len(sorted_props) - 1:
            sorted_props[idx], sorted_props[idx+1] = sorted_props[idx+1], sorted_props[idx]
            
        # Re-assign normalized orders (0, 1, 2...) to ensure clean sequence
        for i, (name, _) in enumerate(sorted_props):
            setattr(scene, name, i)
            
        # Trigger the update
        bpy.ops.fcd.update_panel_order()
        
        # Force immediate redraw of the button list
        context.area.tag_redraw()
        self.report({'INFO'}, f"Moved panel {self.direction}")
        return {'FINISHED'}

class FCD_OT_ResetPanelOrder(bpy.types.Operator):
    """Resets the panel order to default values"""
    bl_idname = "fcd.reset_panel_order"
    bl_label = "Reset Order"
    bl_description = "Resets all panel order settings to their defaults"
    
    def execute(self, context):
        scene = context.scene
        scene.fcd_order_ai_factory = 0     # 1: Generate
        scene.fcd_order_assets = 1         # 2: Asset Library
        scene.fcd_order_parts = 2          # 3: Mechanical Presets
        scene.fcd_order_electronics = 3    # 4: Electronic Presets
        scene.fcd_order_architectural = 4  # 5: Architectural Presets
        scene.fcd_order_vehicle = 5        # 6: Vehicle Presets
        scene.fcd_order_procedural = 6     # 7: Procedural Toolkit
        scene.fcd_order_dimensions = 7     # 8: Dimensions & Precision Transforms
        scene.fcd_order_materials = 8      # 9: Materials & Textures
        scene.fcd_order_physics = 9        # 10: Physics
        scene.fcd_order_kinematics = 10    # 11: Kinematics Setup
        scene.fcd_order_transmission = 11  # 12: Transmission
        scene.fcd_order_lighting = 12      # 13: Environment & Lighting
        scene.fcd_order_camera = 13        # 14: Camera Studio & Pathing
        scene.fcd_order_export = 14        # 15: Export System
        scene.fcd_order_preferences = 15   # 16: Preferences
        
        # Trigger the update to apply changes immediately
        bpy.ops.fcd.update_panel_order()
        return {'FINISHED'}

class UI_UL_WrapItems(bpy.types.UIList):
    def draw_item(self, context: bpy.types.Context, layout: bpy.types.UILayout, data: Any, item: Any, icon: int, active_data: Any, active_propname: str, index: int) -> None:
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            # FIX: Safely display the target object. Using 'prop' on the item's pointer
            # is safer than accessing attributes of the pointer's value (which could be None).
            row.prop(item, "target", text="", emboss=False)
            op = row.operator("fcd.chain_remove_wrap_object", text="", icon='X')
            op.index = index
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


# ------------------------------------------------------------------------
#   PANEL: GENERATE ROBOT (AI FACTORY)
#   Order: 1
#   Description: Main interface for AI-driven robot generation.
# ------------------------------------------------------------------------

def register():
    for cls in [FCD_OT_UpdatePanelOrder, FCD_OT_ToggleTextPlacement, FCD_OT_MovePanel, FCD_OT_ResetPanelOrder, UI_UL_WrapItems]:
        if hasattr(cls, 'bl_rna'):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass

def unregister():
    for cls in reversed([FCD_OT_UpdatePanelOrder, FCD_OT_ToggleTextPlacement, FCD_OT_MovePanel, FCD_OT_ResetPanelOrder, UI_UL_WrapItems]):
        if hasattr(cls, 'bl_rna'):
            bpy.utils.unregister_class(cls)

