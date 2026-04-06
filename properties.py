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

def update_joint_radius(self, context):
    """Refreshes the joint tool visual state when radius changes."""
    update_joint_tool_live(self, context)

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

# --- Joint Editor Tool Dispatchers (Support Targeted Property Application) ---
def dispatch_apply_joint_settings():
    """Fallback: Apply all tool settings to selection."""
    bpy.ops.lsd.apply_joint_settings()
    return None

def dispatch_apply_joint_type():
    """Targeted: Apply only type and axis settings."""
    bpy.ops.lsd.apply_joint_settings(apply_type=True, apply_axis=True, apply_radius=False, apply_viz_scale=False, apply_limits=False, apply_ik=False)
    return None

def dispatch_apply_joint_radius():
    """Targeted: Apply only the joint radius setting."""
    bpy.ops.lsd.apply_joint_settings(apply_type=False, apply_axis=False, apply_radius=True, apply_viz_scale=False, apply_limits=False, apply_ik=False)
    return None

def dispatch_apply_joint_viz_scale():
    """Targeted: Apply only the visual gizmo scale setting."""
    bpy.ops.lsd.apply_joint_settings(apply_type=False, apply_axis=False, apply_radius=False, apply_viz_scale=True, apply_limits=False, apply_ik=False)
    return None

def dispatch_apply_joint_limits():
    """Targeted: Apply only the motion limits (lower/upper)."""
    bpy.ops.lsd.apply_joint_settings(apply_type=False, apply_axis=False, apply_radius=False, apply_viz_scale=False, apply_limits=True, apply_ik=False)
    return None

def dispatch_apply_joint_ik():
    """Targeted: Apply only the IK chain length setting."""
    bpy.ops.lsd.apply_joint_settings(apply_type=False, apply_axis=False, apply_radius=False, apply_viz_scale=False, apply_limits=False, apply_ik=True)
    return None

def dispatch_apply_bone_constraints():

    bpy.ops.lsd.apply_bone_constraints()
    return None

def update_joint_type_live(self, context):
    """Timer-based dispatcher for joint type changes."""
    from . import core
    if isinstance(self.id_data, bpy.types.Scene) and not core._joint_editor_update_guard:
        bpy.app.timers.register(dispatch_apply_joint_type, first_interval=0.01)

def update_joint_radius_live(self, context):
    """Timer-based dispatcher for joint radius changes."""
    from . import core
    if isinstance(self.id_data, bpy.types.Scene) and not core._joint_editor_update_guard:
        bpy.app.timers.register(dispatch_apply_joint_radius, first_interval=0.01)

def update_joint_viz_scale_live(self, context):
    """Timer-based dispatcher for visual gizmo scale changes."""
    from . import core
    if isinstance(self.id_data, bpy.types.Scene) and not core._joint_editor_update_guard:
        bpy.app.timers.register(dispatch_apply_joint_viz_scale, first_interval=0.01)

def update_joint_limits_live(self, context):
    """Timer-based dispatcher for limit changes."""
    from . import core
    if isinstance(self.id_data, bpy.types.Scene) and not core._joint_editor_update_guard:
        bpy.app.timers.register(dispatch_apply_joint_limits, first_interval=0.01)

def update_joint_ik_live(self, context):
    """Timer-based dispatcher for IK changes."""
    from . import core
    if isinstance(self.id_data, bpy.types.Scene) and not core._joint_editor_update_guard:
        bpy.app.timers.register(dispatch_apply_joint_ik, first_interval=0.01)

def update_joint_tool_live(self, context):

                # Transitioning to a timer avoids "readonly mode" errors.
                # Named function prevents multiple identical timers.
                bpy.app.timers.register(dispatch_apply_bone_constraints, first_interval=0.01)

def update_placement_mode_wrapper(self, context):

    """Lean dispatcher for placement mode state change."""
    from . import core
    core.toggle_placement_parenting(self, context)

def update_text_color(self, context):

    """Updates dimension material colors."""
    if hasattr(self, "id_data") and self.id_data.get("lsd_is_dimension"):

        from . import core
        core.get_or_create_text_material(self.id_data)
        self.id_data.update_tag()

def update_curve_orientation_timer(self, context):
    """Dispatches curve vertex rotation via timer."""
    from . import core
    if getattr(core, "_curve_update_guard", False): return
    
    def dispatch():
        core.apply_curve_vertex_rotation(context)
        return None
        
    bpy.app.timers.register(dispatch, first_interval=0.01)

def update_path_align_timer(self, context):
    """Dispatches path vertex alignment via timer."""
    from . import core
    if getattr(core, "_path_align_update_guard", False): return
    if not getattr(self, "lsd_path_live_align", False): return
    
    def dispatch():
        core.apply_path_vertex_alignment(context)
        return None
        
    bpy.app.timers.register(dispatch, first_interval=0.01)



# AI Editor Note: Batch update guard to avoid infinite property feedback loops 
# between grouped dimension items.
_lsd_is_batch_updating = False

_lsd_is_batch_updating = False

def dispatch_batch_dimension_sync():
    """Unified Batch Dispatcher: Processes all pending drafting updates in a single frame."""
    from . import core
    if not core._dim_pending_batch_sync_ids: return None
    
    # 1. Collect and Clear
    targets = list(core._dim_pending_batch_sync_ids)
    core._dim_pending_batch_sync_ids.clear()
    
    # 2. Atomic Evaluation (Ensures all matrices are correct BEFORE we start)
    bpy.context.view_layer.update()
    
    # 3. Process
    for obj_id in targets:
        obj = bpy.data.objects.get(obj_id)
        if obj:
            # We refresh BOTH length and visuals to ensure total consistency
            core.update_dimension_length(obj)
            core.update_arrow_settings(obj)
            obj.update_tag()
            
    return None

def queue_batch_sync(obj_id: str):
    """Adds an object to the batch queue and ensures a timer is running."""
    from . import core
    if not obj_id: return
    
    # If set is empty, it means no timer is currently pending 
    # to process these specifically.
    fire_timer = len(core._dim_pending_batch_sync_ids) == 0
    core._dim_pending_batch_sync_ids.add(obj_id)
    
    if fire_timer:
        bpy.app.timers.register(dispatch_batch_dimension_sync, first_interval=0.01)

def update_arrow_settings_timer(self, context):
    """Optimized Batch Visual Update: Groups visual changes (arrow/text) for bulk syncing."""
    from . import core
    global _lsd_is_batch_updating
    obj = self.id_data
    if not obj: return
    
    # 1. Selection & Group Propagation (Batch Sync)
    if not _lsd_is_batch_updating and context:
         _lsd_is_batch_updating = True
         try:
             # Target candidates: Combine Grouped Items and Viewport Selection
             sync_targets = set()
             
             # A. Grouped Sets
             for g_set in context.scene.lsd_dimensions_grouped_sets:
                  if any(item.obj == obj for item in g_set.items):
                       for item in g_set.items:
                            if item.obj and item.obj != obj:
                                sync_targets.add(item.obj)
             
             # B. Viewport Selection
             from . import core
             for o in context.selected_objects:
                 host = core.get_dimension_host(o)
                 if host and host != obj:
                     sync_targets.add(host)

             # C. Execute Propagation
             for target in sync_targets:
                 sibling_props = getattr(target, "lsd_pg_dim_props", None)
                 # AI Editor Note: User Request - Only sync if NOT manual
                 if sibling_props and not sibling_props.is_manual:
                      sibling_props.arrow_scale = self.arrow_scale
                      sibling_props.text_scale = self.text_scale
                      sibling_props.text_offset = self.text_offset
                      sibling_props.line_thickness = self.line_thickness
                      sibling_props.offset = self.offset
                      # Extended Set
                      sibling_props.font_name = self.font_name
                      sibling_props.font_bold = self.font_bold
                      sibling_props.font_italic = self.font_italic
                      sibling_props.flip_text = self.flip_text
                      sibling_props.is_flipped = self.is_flipped
                      sibling_props.use_extension_lines = self.use_extension_lines
                      sibling_props.text_alignment = self.text_alignment
                      sibling_props.align_x = self.align_x
                      sibling_props.align_nx = self.align_nx
                      sibling_props.align_y = self.align_y
                      sibling_props.align_ny = self.align_ny
                      sibling_props.align_z = self.align_z
                      sibling_props.align_nz = self.align_nz
                      # 2. Drafting Orientation
                      sibling_props.direction = self.direction
         finally:
             _lsd_is_batch_updating = False


    queue_batch_sync(obj.name)

def update_dim_is_flipped(self, context):
    """Callback for 'Flip Target Roles': Synchronizes the 'Flip Text' property."""
    # Toggle the 'Flip Text' property to maintain visual orientation relative to the new direction.
    self.flip_text = not self.flip_text
    update_arrow_settings_timer(self, context)

def update_collision_visibility(self, context):
    """Toggles visibility for all objects in the Physics_Collisions collection."""
    coll = bpy.data.collections.get("Physics_Collisions")
    if not coll: return None
    show = self.lsd_show_collisions
    for obj in coll.objects:
        if obj.name.startswith("COLL_"):
            obj.hide_set(not show)
            obj.hide_viewport = not show
    return None

def update_dimension_length_timer(self, context):
    """Optimized Batch Length Update: Groups multi-dimension length changes into a single frame."""
    from . import core
    global _lsd_is_batch_updating
    obj = self.id_data
    if not obj: return
    
    # 1. Selection & Group Propagation (Batch Sync)
    if not _lsd_is_batch_updating and context:
         _lsd_is_batch_updating = True
         try:
             sync_targets = set()
             
             # A. Grouped Sets
             for g_set in context.scene.lsd_dimensions_grouped_sets:
                  if any(item.obj == obj for item in g_set.items):
                       for item in g_set.items:
                            if item.obj and item.obj != obj:
                                 sync_targets.add(item.obj)
             
             # B. Viewport Selection
             for o in context.selected_objects:
                 from . import core
                 host = core.get_dimension_host(o)
                 if host and host != obj:
                      sync_targets.add(host)

             # C. Execute Propagation
             for target in sync_targets:
                 sibling_props = getattr(target, "lsd_pg_dim_props", None)
                 # AI Editor Note: Only sync if NOT manual
                 if sibling_props and not sibling_props.is_manual:
                      sibling_props.length = self.length
                      sibling_props.unit_display = self.unit_display
         finally:
             _lsd_is_batch_updating = False

    if hasattr(self, "is_manual"):
        self.is_manual = True

    queue_batch_sync(obj.name)

def update_dimension_driver_target(self, context):
    """Sets up a driver for the dimension to follow the target dimension's length."""
    host = self.obj
    target = self.driver_target
    
    if not host or not hasattr(host, "lsd_pg_dim_props"):
        return
        
    target_path = 'lsd_pg_dim_props.length'
    host.driver_remove(target_path)

    if target:
        # 1. Self-Link Guard (Prevents Dependency Cycles)
        if host == target or (host.parent and host.parent == target):
            self.driver_target = None
            return
            
        # Find the actual label object if target is a root
        target_obj = target
        if target.get("lsd_is_dimension_root"):
            for child in target.children:
                if child.get("lsd_is_dimension"):
                    target_obj = child
                    break
        
        # 2. Immediate Sync (Copy length once)
        if hasattr(target_obj, "lsd_pg_dim_props"):
             host.lsd_pg_dim_props.is_manual = True # AI Editor Note: Must be manual to prevent sync fighting
             host.lsd_pg_dim_props.length = target_obj.lsd_pg_dim_props.length
        
        # 3. Establish Persistent Driver
        drv = host.driver_add(target_path).driver
        var = drv.variables.new()
        var.name = 'target_len'
        var.type = 'SINGLE_PROP'
        v_target = var.targets[0]
        v_target.id = target_obj
        v_target.data_path = 'lsd_pg_dim_props.length'
        drv.expression = 'target_len'
        
        # Force update
        host.update_tag()
    else:
        # If unlinked, we can optionally return to dynamic mode
        if host and hasattr(host, "lsd_pg_dim_props"):
             host.lsd_pg_dim_props.is_manual = False
             host.update_tag()

def update_collision_sync_all(self, context, prop_name: str, mod_name: str, mod_type: str, attr_name: str):

    """Generic helper to sync collision properties across multi-selection via a guard."""
    if context.window_manager.get("_lsd_coll_guard", False):

        return None

    

    context.window_manager["_lsd_coll_guard"] = True
    try:

        val = getattr(self, prop_name)
        targets = context.selected_objects
        if not targets and hasattr(self, "id_data"):

            targets = [self.id_data]

            

        for obj in targets:

            source = obj
            if obj.name.startswith("COLL_") and obj.parent:

                source = obj.parent

            

            if not hasattr(source, "lsd_pg_mech_props"):

                continue

                

            # Sync logical props
            setattr(source.lsd_pg_mech_props.collision, prop_name, val)

                

            # Update modifier
            coll_name = f"COLL_{source.name}"
            coll_obj = bpy.data.objects.get(coll_name)
            if coll_obj:

                mod = coll_obj.modifiers.get(mod_name)
                if mod and mod.type == mod_type:

                    setattr(mod, attr_name, val)

    finally:

        context.window_manager["_lsd_coll_guard"] = False

    return None

def update_collision_decimate(self, context):

    return update_collision_sync_all(self, context, "decimate_ratio", "LSD_Collision_Simplify", 'DECIMATE', 'ratio')

def update_collision_thickness(self, context):

    return update_collision_sync_all(self, context, "thickness", "LSD_Collision_Thickness", 'SOLIDIFY', 'thickness')

def update_element_category(self, context):

    """Resets the element selection to the first alphabetical item of the new category."""
    from .config import ELEMENT_DATA
    cat = self.element_category
    if cat in ELEMENT_DATA:

        elements = sorted(ELEMENT_DATA[cat].keys())
        if elements:

            # Setting this triggers update_element_density automatically
            self.element_type = elements[0]

def update_cursor_local_wrapper(self, context):

    """Lean dispatcher to core module for cursor tool."""
    from . import core
    core.update_local_cursor_from_tool(self, context)

def get_element_type_items(self, context):

    """Callback to return alphabetically sorted elements for the selected category."""
    from .config import ELEMENT_DATA
    cat = getattr(self, "element_category", 'METALS')
    if cat in ELEMENT_DATA:

        elements = sorted(ELEMENT_DATA[cat].keys())
        return [(el, el, f"Density: {ELEMENT_DATA[cat][el]} g/cm³") for el in elements]

    return [('NONE', "None", "")]

def update_element_density(self, context):

    """Updates the custom mass based on the chosen element preset."""
    from .config import ELEMENT_DATA
    cat = self.element_category
    el = self.element_type
    if cat in ELEMENT_DATA and el in ELEMENT_DATA[cat]:

        self.custom_mass_gcm3 = ELEMENT_DATA[cat][el]

# ------------------------------------------------------------------------

#   Property Group Definitions (LSD PG Mandate)

# ------------------------------------------------------------------------

class LSD_PG_Transmission_Properties(bpy.types.PropertyGroup):

    type: bpy.props.StringProperty(name="Type", default="transmission_interface/SimpleTransmission")
    joint: bpy.props.StringProperty(name="Joint")
    hardware_interface: bpy.props.StringProperty(name="Hardware Interface", default="hardware_interface/EffortJointInterface")
    mechanical_reduction: bpy.props.FloatProperty(name="Mechanical Reduction", default=1.0)

class LSD_PG_Material_Properties(bpy.types.PropertyGroup):

    color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', default=(0.8, 0.8, 0.8, 1.0), size=4, min=0.0, max=1.0)
    texture: bpy.props.PointerProperty(name="Texture", type=bpy.types.Image)

class LSD_PG_Slinky_Hook(bpy.types.PropertyGroup):

    name: bpy.props.StringProperty(name="Hook Name")
    target: bpy.props.PointerProperty(type=bpy.types.Object, name="Target")

class LSD_PG_Wrap_Item(bpy.types.PropertyGroup):

    name: bpy.props.StringProperty(name="Item Name")
    obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Object")

class LSD_PG_Collision_Properties(bpy.types.PropertyGroup):

    shape: bpy.props.EnumProperty(name="Shape", items=[('BOX', "Box", ""), ('CYLINDER', "Cylinder", ""), ('SPHERE', "Sphere", ""), ('MESH', "Mesh", "")], default='MESH')
    collision_object: bpy.props.PointerProperty(name="Collision Object", type=bpy.types.Object)
    decimate_ratio: bpy.props.FloatProperty(
        name="Simplification Ratio", 
        description="Ratio of triangles to keep (1.0 = original, 0.1 = 10% polygons)", 
        default=1.0, min=0.0, max=1.0, 
        update=update_collision_decimate

    )
    thickness: bpy.props.FloatProperty(
        name="Collision Thickness",
        description="Offset distance/shell thickness relative to original mesh",
        default=0.0, min=0.0, unit='LENGTH',
        update=update_collision_thickness
    )

class LSD_PG_Inertial_Properties(bpy.types.PropertyGroup):

    # Element Preset Selection
    element_category: bpy.props.EnumProperty(
        name="Category",
        items=[('METALS', "Metals", ""), ('NONMETALS', "Nonmetals", ""), ('SEMIMETALS', "Semimetals", "")],
        default='METALS',
        update=update_element_category

    )
    element_type: bpy.props.EnumProperty(
        name="Material Preset",
        items=get_element_type_items,
        update=update_element_density
    )

    

    # Redundant but kept for internal calculations
    mass: bpy.props.FloatProperty(name="Mass (kg)", default=1.0, min=0.0)

    

    # Primary User Input (Formerly mass_gcm3 / density_gcm3)
    custom_mass_gcm3: bpy.props.FloatProperty(name="Custom Mass (g/cm³)", default=1.0, min=0.0)

    

    volume_m3: bpy.props.FloatProperty(name="Calculated Volume", default=0.0)
    center_of_mass: bpy.props.FloatVectorProperty(name="Center of Mass", subtype='TRANSLATION', unit='LENGTH', size=3)
    ixx: bpy.props.FloatProperty(name="Ixx", default=1.0)
    iyy: bpy.props.FloatProperty(name="Iyy", default=1.0)
    izz: bpy.props.FloatProperty(name="Izz", default=1.0)
    ixy: bpy.props.FloatProperty(name="Ixy", default=0.0)
    ixz: bpy.props.FloatProperty(name="Ixz", default=0.0)
    iyz: bpy.props.FloatProperty(name="Iyz", default=0.0)

class LSD_PG_Wrap_Item(bpy.types.PropertyGroup):
    target: bpy.props.PointerProperty(type=bpy.types.Object, name="Wrap Object")

class LSD_PG_Dimensions_Master_Item(bpy.types.PropertyGroup):
    """Represents an entry in the Dimension Master Interface list."""
    obj: bpy.props.PointerProperty(type=bpy.types.Object, name="Dimension")
    driver_target: bpy.props.PointerProperty(
        type=bpy.types.Object, 
        name="Link Source",
        description="Link Source - Pick another dimension to mirror its length.",
        poll=lambda self, obj: obj.get("lsd_is_dimension") or obj.get("lsd_is_dimension_root"),
        update=update_dimension_driver_target
    )

class LSD_PG_Dimension_Props(bpy.types.PropertyGroup):

    """
    Parametric properties for dimension labels and arrow heads.
    Uses timer-based updates to maintain UI responsiveness.
    """
    arrow_scale: bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.001, update=update_arrow_settings_timer)
    text_scale: bpy.props.FloatProperty(name="Text Size", default=0.1, min=0.0, update=update_arrow_settings_timer)
    text_offset: bpy.props.FloatProperty(name="Text Offset", description="Distance between the label and the dimension line", default=0.05, min=0.0, unit='LENGTH', update=update_arrow_settings_timer)
    line_thickness: bpy.props.FloatProperty(name="Line Thickness", default=0.002, min=0.0, unit='LENGTH', update=update_arrow_settings_timer)
    offset: bpy.props.FloatProperty(name="Offset from Target", default=0.1, unit='LENGTH', update=update_arrow_settings_timer)
    text_color: bpy.props.FloatVectorProperty(name="Label Color", subtype='COLOR', default=(0.0, 0.0, 0.0, 1.0), size=4, min=0.0, max=1.0, update=update_text_color)
    unit_display: bpy.props.EnumProperty(name="Units", items=[('METERS', "Meters (m)", ""), ('MM', "Millimeters (mm)", "")], default='METERS', update=update_dimension_length_timer)
    length: bpy.props.FloatProperty(name="Line Length", default=1.0, unit='LENGTH', update=update_dimension_length_timer)
    direction: bpy.props.EnumProperty(name="Direction", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], default='Z', update=update_arrow_settings_timer)
    is_flipped: bpy.props.BoolProperty(name="Flip Target Roles", default=False, update=update_dim_is_flipped)

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
    font_name: bpy.props.EnumProperty(
        name="Font Type",
        items=[
            ('DEFAULT', "Default Blender Font", ""),
            # Geometric & Modern
            ('FUTURA', "Futura", "Geometric sans-serif favored for its modern look"),
            ('HELVETICA', "Helvetica / Neue", "Known for neutrality and high readability"),
            ('DIN', "DIN 1451", "Standard German technical font for engineering"),
            ('CENTURY', "Century Gothic", "Modern, wide-set, and minimalist"),
            ('ARIAL', "Arial / Narrow", "Standard construction document font"),
            ('GOTHAM', "Gotham", "Inspired by architectural signage"),
            ('AVENIR', "Avenir", "Geometric style with humanistic proportions"),
            ('ROBOTO', "Roboto", "Modern digital-first font"),
            ('CONSOLAS', "Consolas", "Technical explanatory text font"),
            # CAD-Specific & Technical
            ('SIMPLEX', "Simplex", "Clean, single-line CAD font"),
            ('ARCHITXT', "Architxt", "Handwriting-style technical font"),
            ('ROMANS', "RomanS", "Professional legible CAD font"),
            ('CITY', "City Blueprint", "Standard CAD font with technical feel"),
            ('ISO', "ISOCPEUR", "ISO 3098 standard technical font"),
            ('STYLUS', "Stylus BT", "Hand-lettered CAD appearance"),
            # Portfolio & Presentation
            ('ARCH_DAUGHTER', "Architect's Daughter", "Mimics hand-lettering"),
            ('POPPINS', "Poppins", "Bold headers font"),
            ('QUICKSAND', "Quicksand", "Minimalist captions font"),
            ('BAUHAUS', "Bauhaus 93", "Decorative typeface for titles"),
            ('SPACE', "Space Grotesk", "High-impact headers"),
            ('MONTSERRAT', "Montserrat", "Design-centric branding font")
        ],
        default='DEFAULT',
        update=update_arrow_settings_timer

    )
    font_bold: bpy.props.BoolProperty(
        name="Bold",
        description="Apply bold style to the dimension text (requires bold variant of the font)",
        default=False,
        update=update_arrow_settings_timer
    )
    font_italic: bpy.props.BoolProperty(
        name="Italic",
        description="Apply italic style to the dimension text (requires italic variant of the font)",
        default=False,
        update=update_arrow_settings_timer
    )
    text_alignment: bpy.props.EnumProperty(
        name="Text Alignment",
        items=[('LEFT', "Left", ""), ('CENTER', "Center", ""), ('RIGHT', "Right", "")],
        default='CENTER',
        update=update_arrow_settings_timer

    )

class LSD_PG_Mech_Props(bpy.types.PropertyGroup):

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
    slinky_hooks: bpy.props.CollectionProperty(type=LSD_PG_Slinky_Hook)
    slinky_active_index: bpy.props.IntProperty(default=0)

    

    # 5. CHAINS & BELTS EXTENDED
    chain_drive_target: bpy.props.PointerProperty(type=bpy.types.Object, name="Drive Source")
    chain_drive_ratio: bpy.props.FloatProperty(name="Drive Ratio", default=1.0)
    chain_drive_invert: bpy.props.BoolProperty(name="Invert Drive", default=False)
    wrap_picker: bpy.props.PointerProperty(type=bpy.types.Object, name="Wrap Object")
    chain_wrap_items: bpy.props.CollectionProperty(type=LSD_PG_Wrap_Item)
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
    collision: bpy.props.PointerProperty(type=LSD_PG_Collision_Properties)
    inertial: bpy.props.PointerProperty(type=LSD_PG_Inertial_Properties)
    material: bpy.props.PointerProperty(type=LSD_PG_Material_Properties)

class LSD_PG_Mimic_Driver(bpy.types.PropertyGroup):

    target_bone: bpy.props.StringProperty(name="Target")
    ratio: bpy.props.FloatProperty(name="Ratio", default=1.0)

class LSD_PG_Kinematic_Props(bpy.types.PropertyGroup):

    collision: bpy.props.PointerProperty(type=LSD_PG_Collision_Properties)
    inertial: bpy.props.PointerProperty(type=LSD_PG_Inertial_Properties)
    material: bpy.props.PointerProperty(type=LSD_PG_Material_Properties)
    transmission: bpy.props.PointerProperty(type=LSD_PG_Transmission_Properties)

    joint_type: bpy.props.EnumProperty(
        name="Joint Type",
        items=[('none', "None", ""), ('base', "Base", ""), ('fixed', "Fixed", ""), ('revolute', "Revolute", ""), ('continuous', "Continuous", ""), ('prismatic', "Linear", ""), ('spherical', "Spherical", "")], 
        default='none',
        update=update_joint_type_live

    )
    axis_alignment: bpy.props.EnumProperty(
        name="Axis Alignment",
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('-X', "-X", ""), ('-Y', "-Y", ""), ('-Z', "-Z", "")], 
        default='Z',
        update=update_joint_type_live

    )
    joint_radius: bpy.props.FloatProperty(name="Joint Radius", default=0.05, min=0.0, unit='LENGTH', update=update_joint_radius_live)
    visual_gizmo_scale: bpy.props.FloatProperty(name="Visual Gizmo Scale", default=1.0, min=0.0, update=update_joint_viz_scale_live)
    lower_limit: bpy.props.FloatProperty(name="Lower Limit", default=-90.0, update=update_joint_limits_live)
    upper_limit: bpy.props.FloatProperty(name="Upper Limit", default=90.0, update=update_joint_limits_live)
    ik_chain_length: bpy.props.IntProperty(name="IK Chain Length", default=0, min=0, max=255, update=update_joint_ik_live)
    ratio_value: bpy.props.FloatProperty(name="Ratio", default=1.0)
    ratio_target_bone: bpy.props.StringProperty(name="Target Bone")
    ratio_ref_bone: bpy.props.StringProperty(name="Ref Bone")
    ratio_invert: bpy.props.BoolProperty(name="Invert", default=False)
    mimic_drivers: bpy.props.CollectionProperty(type=LSD_PG_Mimic_Driver)
    mimic_drivers_index: bpy.props.IntProperty(default=0)

class LSD_PG_AI_Props(bpy.types.PropertyGroup):

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

class LSD_PG_Lighting_Props(bpy.types.PropertyGroup):

    light_preset: bpy.props.EnumProperty(name="Preset", items=[('STUDIO', "Studio", ""), ('OUTDOOR', "Outdoor", ""), ('EMPTY', "Ambient", "")], default='STUDIO')
    background_color: bpy.props.FloatVectorProperty(name="Background", subtype='COLOR', size=4, default=(0.04, 0.04, 0.04, 1.0))
    base_color: bpy.props.FloatVectorProperty(name="Tint", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0))
    light_intensity: bpy.props.FloatProperty(name="Intensity", default=1.0, min=0.0)
    use_shadows: bpy.props.BoolProperty(name="Use Shadows", default=True)

    

    # Selected Light Editor State (AI Added)
    selected_light_type: bpy.props.EnumProperty(name="Type", items=[('POINT', "Point", ""), ('SUN', "Sun", ""), ('SPOT', "Spot", ""), ('AREA', "Area", "")], default='POINT')
    selected_light_shading: bpy.props.EnumProperty(name="Shading", items=[('FLAT', "Flat", ""), ('GRADIENT', "Gradient", "")], default='GRADIENT')
    selected_light_energy: bpy.props.FloatProperty(name="Power", default=100.0, min=0.0)
    selected_light_color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0))
    selected_light_target: bpy.props.PointerProperty(name="Target", type=bpy.types.Object)

class LSD_PG_Asset_Props(bpy.types.PropertyGroup):

    target_library: bpy.props.StringProperty(name="Library Path", description="Library folder used for marking and importing assets.")
    selected_catalog: bpy.props.StringProperty(name="Catalog", description="Choose a catalog folder within the selected library.")

    

    # Path/Management properties used in sidebars/popups
    add_library_path: bpy.props.StringProperty(name="New Library Path", description="Path to a folder to be added as a new Asset Library.")
    new_catalog_name: bpy.props.StringProperty(name="Catalog Name", description="Name for the new asset catalog folder.")

    

    # Batch Import settings
    import_source_filepath: bpy.props.StringProperty(name="Import File", description="Select a 3D file (.blend, .fbx, .glb) to import.", subtype='FILE_PATH')
    import_target_library: bpy.props.StringProperty(name="Target Library", description="Library where the imported file will be registered.")
    import_target_catalog: bpy.props.StringProperty(name="Target Catalog", description="Catalog folder where the imported file will be added.")

class LSD_PG_Dimensions_Grouped_Set(bpy.types.PropertyGroup):
    """A persistent group of dimension controllers with its own name and items."""
    name: bpy.props.StringProperty(name="Set Name", default="Drafting Group")
    items: bpy.props.CollectionProperty(type=LSD_PG_Dimensions_Master_Item)
    is_expanded: bpy.props.BoolProperty(default=True)

class LSD_ExportItem(bpy.types.PropertyGroup):

    """Item for the export list"""
    rig: bpy.props.PointerProperty(type=bpy.types.Object, name="Rig")

# ------------------------------------------------------------------------

#   Registration

# ------------------------------------------------------------------------

CLASSES = [
    LSD_PG_Transmission_Properties, LSD_PG_Material_Properties, LSD_PG_Collision_Properties,
    LSD_PG_Inertial_Properties, LSD_PG_Wrap_Item, LSD_PG_Dimensions_Master_Item, LSD_PG_Dimensions_Grouped_Set, LSD_PG_Slinky_Hook, LSD_PG_Mech_Props, LSD_PG_Mimic_Driver,
    LSD_PG_Kinematic_Props, LSD_PG_AI_Props, LSD_PG_Lighting_Props, LSD_PG_Asset_Props,
    LSD_PG_Dimension_Props, LSD_ExportItem
]

def register():

    for cls in CLASSES:

        try:

            bpy.utils.register_class(cls)

        except Exception as e:

            print(f"Warning: LSD could not register {cls.__name__}: {e}")

    

    # Pointers
    bpy.types.Object.lsd_pg_mech_props = bpy.props.PointerProperty(type=LSD_PG_Mech_Props)
    bpy.types.PoseBone.lsd_pg_kinematic_props = bpy.props.PointerProperty(type=LSD_PG_Kinematic_Props)
    # Scene
    bpy.types.Scene.lsd_pg_ai_props = bpy.props.PointerProperty(type=LSD_PG_AI_Props)
    bpy.types.Scene.lsd_pg_lighting_props = bpy.props.PointerProperty(type=LSD_PG_Lighting_Props)
    bpy.types.Scene.lsd_pg_asset_props = bpy.props.PointerProperty(type=LSD_PG_Asset_Props)
    bpy.types.Scene.lsd_pg_joint_editor_settings = bpy.props.PointerProperty(type=LSD_PG_Kinematic_Props)
    bpy.types.Object.lsd_pg_dim_props = bpy.props.PointerProperty(type=LSD_PG_Dimension_Props)

    

    # Precision Scale State (Drafting)
    def update_accurate_scale(self, context):
        """Real-time drafting sync: Applying scale as parameters change."""
        if getattr(context.scene, 'lsd_scale_realtime', True) and context.active_object:
             # Calling the operator ensures BMesh and Object mode safety
             bpy.ops.lsd.accurate_scale()

    bpy.types.Scene.lsd_scale_realtime = bpy.props.BoolProperty(
        name="Live Calibration",
        description="Automatically apply scaling as parameters change",
        default=True
    )
    bpy.types.Scene.lsd_scale_axes = bpy.props.BoolVectorProperty(
        name="Scale Axes", size=3, default=(True, True, True),
        update=update_accurate_scale
    )
    bpy.types.Scene.lsd_scale_value = bpy.props.FloatProperty(name="Value", default=1.0, min=0.0001, subtype='DISTANCE', update=update_accurate_scale)
    bpy.types.Scene.lsd_scale_mode = bpy.props.EnumProperty(
        name="Scaling Mode",
        items=[('GROUP', "Group", "Scale selected objects as a single unit"), ('INDIVIDUAL', "Individual", "Scale each selected object separately")],
        default='GROUP',
        update=update_accurate_scale
    )
    bpy.types.Scene.lsd_scale_pivot = bpy.props.EnumProperty(
        name="Pivot Point",
        items=[('ORIGIN', "Origin / Center", "Scale around active object origin or selection center"), ('CURSOR', "3D Cursor", "Scale around the current cursor location")],
        default='CURSOR',
        update=update_accurate_scale
    )

    

    # UI Visibility (Initialize/Reset)
    from .config import LSD_PANEL_PROPS, MECH_CATEGORIES_SORTED, ELECTRONICS_CATEGORIES, ALL_ELECTRONICS_TYPES, ARCHITECTURAL_TYPES, VEHICLE_TYPES, GIZMO_STYLES, BONE_MODES, BONE_AXES

    

    # 1. Selection & Utility Properties
    bpy.types.Scene.lsd_part_category = bpy.props.EnumProperty(name="Category", items=MECH_CATEGORIES_SORTED)

    

    def lsd_part_type_items(self, context):

        cat = getattr(self, "lsd_part_category", 'GEAR')
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

    bpy.types.Scene.lsd_part_type = bpy.props.EnumProperty(name="Type", items=lsd_part_type_items)
    bpy.types.Scene.lsd_electronics_category = bpy.props.EnumProperty(name="Category", items=ELECTRONICS_CATEGORIES)
    bpy.types.Scene.lsd_electronics_type = bpy.props.EnumProperty(name="Type", items=ALL_ELECTRONICS_TYPES)
    bpy.types.Scene.lsd_architectural_type = bpy.props.EnumProperty(name="Type", items=ARCHITECTURAL_TYPES)
    bpy.types.Scene.lsd_vehicle_type = bpy.props.EnumProperty(name="Type", items=VEHICLE_TYPES)

    

    bpy.types.Scene.lsd_use_generation_cage = bpy.props.BoolProperty(name="Use Size Cage", default=False)
    bpy.types.Scene.lsd_generation_cage_size = bpy.props.FloatProperty(name="Max Dimension", default=0.2, unit='LENGTH')

    

    bpy.types.Scene.lsd_viz_gizmos = bpy.props.BoolProperty(name="Show Gizmos", default=True)
    bpy.types.Scene.lsd_show_bones = bpy.props.BoolProperty(name="Show Bones", default=True)
    bpy.types.Scene.lsd_auto_collapse_panels = bpy.props.BoolProperty(name="Auto-Collapse", default=True)
    bpy.types.Scene.lsd_text_placement_mode = bpy.props.BoolProperty(name="Text Placement", default=False)
    bpy.types.Scene.lsd_placement_mode = bpy.props.BoolProperty(name="Object Placement", default=False, update=update_placement_mode_wrapper)

    

    bpy.types.Scene.lsd_gizmo_style = bpy.props.EnumProperty(name="Style", items=GIZMO_STYLES, default='DEFAULT')
    bpy.types.Scene.lsd_bone_mode = bpy.props.EnumProperty(name="Mode", items=BONE_MODES, default='INDIVIDUAL')
    bpy.types.Scene.lsd_bone_axis = bpy.props.EnumProperty(name="Axis", items=BONE_AXES, default='AUTO')
    bpy.types.Scene.lsd_cursor_local_pos = bpy.props.FloatVectorProperty(name="Local Pos", size=3, unit='LENGTH', update=update_cursor_local_wrapper)
    bpy.types.Scene.lsd_active_rig = bpy.props.PointerProperty(type=bpy.types.Object, name="Active Rig")

    

    bpy.types.Scene.lsd_camera_preset = bpy.props.EnumProperty(
        name="Camera Preset",
        items=[
            ('35MM', "35mm Standard", "Standard full-frame lens"),
            ('70MM', "70mm Telephoto", "Longer lens for cinematic depth"),
            ('16MM', "16mm Ultra-Wide", "Action camera style (GoPro)"),
            ('8MM', "8mm Security", "Wide surveillance lens"),
        ],
        default='35MM'

    )

    

    # 1.2 Collision Globals
    bpy.types.Scene.lsd_show_collisions = bpy.props.BoolProperty(name="Show Collisions", default=True, update=update_collision_visibility)

    

    # 1.1 Dimension Globals (LSD Scoped)
    bpy.types.Scene.lsd_dim_arrow_scale = bpy.props.FloatProperty(name="Arrow Scale", default=0.1, min=0.01)
    bpy.types.Scene.lsd_dim_text_scale = bpy.props.FloatProperty(name="Text Scale", default=0.1, min=0.01)
    bpy.types.Scene.lsd_dim_text_offset = bpy.props.FloatProperty(name="Text Offset", default=0.05, min=0.0, unit='LENGTH')
    bpy.types.Scene.lsd_dim_line_thickness = bpy.props.FloatProperty(name="Line Thickness", default=0.002, min=0.0, unit='LENGTH')
    bpy.types.Scene.lsd_dim_offset = bpy.props.FloatProperty(name="Offset", default=0.1, min=0.0, unit='LENGTH')
    bpy.types.Scene.lsd_dim_axis = bpy.props.EnumProperty(
        name="Measurement Axis", 
        items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", ""), ('ALL', "All Axes", "")], 
        default='ALL'
    )
    # Unified Proportion Ratios (Dynamic Defaults the user can register)
    bpy.types.Scene.lsd_dim_ratio_arrow = bpy.props.FloatProperty(name="Arrow Ratio", default=0.2, min=0.001)
    bpy.types.Scene.lsd_dim_ratio_text = bpy.props.FloatProperty(name="Text Ratio", default=0.1, min=0.001)
    bpy.types.Scene.lsd_dim_ratio_thick = bpy.props.FloatProperty(name="Thick Ratio", default=0.004, min=0.0001)
    bpy.types.Scene.lsd_dim_ratio_text_off = bpy.props.FloatProperty(name="Text Off Ratio", default=0.06, min=0.001)
    bpy.types.Scene.lsd_dim_ratio_offset = bpy.props.FloatProperty(name="Offset Ratio", default=0.15, min=0.001)

    # 1.1.3 Global Color Sync Logic
    def update_dim_color_sync(self, context):
        from . import core
        # Force refresh of all dimension materials in the scene
        for obj in bpy.data.objects:
            if obj.get("lsd_is_dimension"):
                # Color Persistence: If global sync is being disabled, bake the universal color to the local property.
                if not self.lsd_dim_global_text_color_sync:
                    dim_props = getattr(obj, "lsd_pg_dim_props", None)
                    if dim_props:
                        dim_props.text_color = self.lsd_dim_universal_text_color
                core.get_or_create_text_material(obj)

    bpy.types.Scene.lsd_dim_global_text_color_sync = bpy.props.BoolProperty(
        name="Global Color Sync", 
        default=True,
        update=update_dim_color_sync
    )

    bpy.types.Scene.lsd_dim_universal_text_color = bpy.props.FloatVectorProperty(
        name="Universal Label Color", 
        subtype='COLOR', 
        size=4, 
        min=0.0, max=1.0, # Explicit hard-limit for color wheel range
        default=(0.0, 0.0, 0.0, 1.0),
        update=update_dim_color_sync
    )

    # Global Font Defaults for new dimensions and descriptors
    bpy.types.Scene.lsd_dim_font_name = bpy.props.EnumProperty(
        name="Default Font",
        items=[
            ('DEFAULT', "Default Blender Font", ""),
            ('FUTURA', "Futura", ""), ('HELVETICA', "Helvetica", ""), ('DIN', "DIN 1451", ""),
            ('CENTURY', "Century Gothic", ""), ('ARIAL', "Arial", ""), ('GOTHAM', "Gotham", ""),
            ('AVENIR', "Avenir", ""), ('ROBOTO', "Roboto", ""), ('CONSOLAS', "Consolas", ""),
            ('SIMPLEX', "Simplex", ""), ('ARCHITXT', "Architxt", ""), ('ROMANS', "RomanS", ""),
            ('CITY', "City Blueprint", ""), ('ISO', "ISOCPEUR", ""), ('STYLUS', "Stylus BT", ""),
            ('ARCH_DAUGHTER', "Architect's Daughter", ""), ('POPPINS', "Poppins", ""),
            ('TAHOMA', "Tahoma", ""), ('VERDANA', "Verdana", ""), ('SEGOE', "Segoe UI", ""),
            ('TREBUCHET', "Trebuchet MS", ""),
            ('QUICKSAND', "Quicksand", ""), ('BAUHAUS', "Bauhaus 93", ""),
            ('SPACE', "Space Grotesk", ""), ('MONTSERRAT', "Montserrat", "")
        ],
        default='DEFAULT'
    )
    bpy.types.Scene.lsd_dim_font_bold = bpy.props.BoolProperty(name="Default Bold", default=False)
    bpy.types.Scene.lsd_dim_font_italic = bpy.props.BoolProperty(name="Default Italic", default=False)

    

    def update_lsd_visibility(self, context):
        """Global visibility toggle for dimensions and anchors (Hooks/Markers)."""
        hide_anchors = context.scene.lsd_hide_all_anchors
        hide_dims = context.scene.lsd_hide_all_dimensions
        
        for obj in bpy.data.objects:
            anc_type = obj.get("lsd_is_dimension_anchor")
            is_dim = (
                obj.get("lsd_is_dimension") or 
                obj.get("lsd_is_dimension_root") or 
                obj.get("lsd_is_dimension_line") or 
                obj.get("lsd_is_extension_line") or
                anc_type == "VISUAL"
            )
            is_internal_anchor = anc_type in ["MASTER", "HOOK"]
            is_manual_pnt = obj.get("lsd_anchor") or obj.get("lsd_is_marker")
            
            # 1. Native Hide for Anchors (Masters and Manual Hooks)
            if is_manual_pnt or (is_internal_anchor and hide_anchors):
                 obj.hide_set(hide_anchors)
                 # AI Editor Note: Using hide_set (Eye) instead of hide_viewport (Screen)
                 # to ensure property update callbacks still fire during batch edits.
            
            # 2. Native Hide for Dimensions (Whole assembly, including internal anchors)
            if is_dim or is_internal_anchor:
                # To prevent broken lines leading to hidden roots, 
                # INTERNAL anchors must hide whenever the dimension hides.
                h = hide_dims if is_dim else (hide_dims or (is_internal_anchor and hide_anchors))
                obj.hide_set(h)
                
                # AI Editor Note: Recursively ensure children (Extension Lines, Labels, etc.) 
                # follow the root's visibility state even if they lack individual tags.
                if obj.get("lsd_is_dimension_root"):
                     for child in obj.children:
                          child.hide_set(h)
            
            # AI Editor Note: Removed global hide_set(False) reset to prevent un-hiding 
            # objects that were manually hidden by the user outside of the toolkit.

    bpy.types.Scene.lsd_hide_all_anchors = bpy.props.BoolProperty(
        name="Hide All Anchors", 
        default=False,
        update=update_lsd_visibility
    )
    bpy.types.Scene.lsd_hide_all_dimensions = bpy.props.BoolProperty(
        name="Hide All Dimensions", 
        default=False,
        update=update_lsd_visibility
    )

    bpy.types.Scene.lsd_anchor_placement_source = bpy.props.EnumProperty(
        name="Placement Mode",
        items=[('SELECTED', "Selected Origin/Center", ""), ('CURSOR', "3D Cursor", "")],
        default='CURSOR'
    )
    bpy.types.Scene.lsd_anchor_grouping_mode = bpy.props.EnumProperty(
        name="Grouping Mode",
        items=[('GROUP', "Grouped (Single Anchor)", ""), ('INDIVIDUAL', "Individual (Per-Selection)", "")],
        default='GROUP'
    )
    bpy.types.Scene.lsd_anchor_initial_size = bpy.props.FloatProperty(name="Initial Size", default=0.05, min=0.001, unit='LENGTH')
    bpy.types.Scene.lsd_anchor_auto_size = bpy.props.BoolProperty(name="Auto-Size", default=True)
    # 1.1.2 Dimensions Master System (Contextual Control)
    # 1.1.2 Dimensions Master System (Multiple Groups Support)
    bpy.types.Scene.lsd_dimensions_master = bpy.props.CollectionProperty(type=LSD_PG_Dimensions_Master_Item)
    bpy.types.Scene.lsd_dimensions_grouped_sets = bpy.props.CollectionProperty(type=LSD_PG_Dimensions_Grouped_Set)

    # 3. Curve Tools Orientation (Drafting)
    bpy.types.Scene.lsd_curve_vertex_rot = bpy.props.FloatVectorProperty(
        name="Curve Align Rotation",
        subtype='EULER',
        size=3,
        update=update_curve_orientation_timer
    )
    bpy.types.Scene.lsd_curve_vertex_rot_prev = bpy.props.FloatVectorProperty(
        name="Prev Rotation State",
        size=3,
        options={'HIDDEN'}
    )

    # 4. Path Tools Alignment (Drafting)
    bpy.types.Scene.lsd_path_align_pos = bpy.props.BoolVectorProperty(
        name="Align Positives",
        size=3,
        description="Align to bounding box maximums (+X, +Y, +Z)",
        update=update_path_align_timer
    )
    bpy.types.Scene.lsd_path_align_neg = bpy.props.BoolVectorProperty(
        name="Align Negatives",
        size=3,
        description="Align to bounding box minimums (-X, -Y, -Z)",
        update=update_path_align_timer
    )
    bpy.types.Scene.lsd_path_live_align = bpy.props.BoolProperty(
        name="Live Calibration",
        default=False,
        update=update_path_align_timer
    )


    bpy.types.Scene.lsd_export_list_index = bpy.props.IntProperty(default=0)
    bpy.types.Scene.lsd_export_check_meshes = bpy.props.BoolProperty(name="Meshes", default=True)
    bpy.types.Scene.lsd_export_check_textures = bpy.props.BoolProperty(name="Textures", default=True)
    bpy.types.Scene.lsd_export_check_config = bpy.props.BoolProperty(name="Config/URDF", default=True)
    bpy.types.Scene.lsd_export_check_launch = bpy.props.BoolProperty(name="Launch Files", default=True)
    bpy.types.Scene.lsd_export_mesh_format = bpy.props.EnumProperty(name="Format", items=[('STL', "STL", ""), ('DAE', "DAE", ""), ('OBJ', "OBJ", "")], default='STL')
    bpy.types.Scene.lsd_quick_export_format = bpy.props.EnumProperty(name="Quick Format", items=[('STL', "STL", ""), ('DAE', "DAE", ""), ('OBJ', "OBJ", "")], default='STL')

    

    # 3. Material Properties
    bpy.types.Scene.lsd_smart_material_type = bpy.props.EnumProperty(
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
                    bsdf.inputs['Alpha'].default_value = self.lsd_material_transparency

                    

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

                mapping.inputs['Location'].default_value = self.lsd_tex_pos
                mapping.inputs['Rotation'].default_value = (0, 0, self.lsd_tex_rot)
                mapping.inputs['Scale'].default_value = self.lsd_tex_scale

    bpy.types.Scene.lsd_tex_pos = bpy.props.FloatVectorProperty(name="Position", size=3, update=update_tex_transform)
    bpy.types.Scene.lsd_tex_rot = bpy.props.FloatProperty(name="Rotation", update=update_tex_transform)
    bpy.types.Scene.lsd_tex_scale = bpy.props.FloatVectorProperty(name="Scale", size=3, default=(1.0, 1.0, 1.0), update=update_tex_transform)
    bpy.types.Scene.lsd_material_transparency = bpy.props.FloatProperty(
        name="Transparency",
        default=1.0,
        min=0.0,
        max=1.0,
        update=update_material_alpha
    )

    

    bpy.types.Scene.lsd_hook_placement_mode = bpy.props.BoolProperty(name="Hook Placement", default=False)

    

    # 3. Order Properties
    prop_names = [
        "lsd_order_ai_factory",    # 1: Generate
        "lsd_order_assets",        # 2: Asset Library
        "lsd_order_parts",         # 3: Mechanical Presets
        "lsd_order_electronics",   # 4: Electronic Presets
        "lsd_order_architectural", # 5: Architectural Presets
        "lsd_order_vehicle",       # 6: Vehicle Presets
        "lsd_order_procedural",    # 7: Procedural Toolkit
        "lsd_order_dimensions",    # 8: Dimensions & Precision Transforms
        "lsd_order_materials",     # 9: Materials & Textures
        "lsd_order_physics",       # 10: Physics
        "lsd_order_kinematics",    # 11: Kinematics Setup
        "lsd_order_transmission",  # 12: Transmission
        "lsd_order_lighting",      # 13: Environment & Lighting
        "lsd_order_camera",        # 14: Camera Studio & Pathing
        "lsd_order_export",        # 15: Export System
        "lsd_order_preferences"    # 16: Preferences
    ]

    for i, name in enumerate(prop_names):

        setattr(bpy.types.Scene, name, bpy.props.IntProperty(name="Panel Order", default=i))

    # 4. Expansion Toggles
    for prop in LSD_PANEL_PROPS:

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

    """Systematic cleanup of all LSD properties and classes."""
    try:

        # 1. Clean up Scene Properties
        from .config import LSD_PANEL_PROPS
        all_scene_props = LSD_PANEL_PROPS + [
            "lsd_pg_ai_props", "lsd_pg_lighting_props", "lsd_pg_asset_props", "lsd_export_list",
            "lsd_pg_joint_editor_settings",
            "lsd_active_rig", "lsd_viz_gizmos", "lsd_show_bones", "lsd_auto_collapse_panels",
            "lsd_text_placement_mode", "lsd_placement_mode", "lsd_part_category", "lsd_part_type",
            "lsd_electronics_category", "lsd_electronics_type", "lsd_architectural_type", "lsd_vehicle_type",
            "lsd_use_generation_cage", "lsd_generation_cage_size", "lsd_gizmo_style", "lsd_bone_mode",
            "lsd_scale_axes", "lsd_scale_value",
            "lsd_bone_axis", "lsd_cursor_local_pos", "lsd_export_list_index", "lsd_export_check_meshes",
            "lsd_export_check_textures", "lsd_export_check_config", "lsd_export_check_launch",
            "lsd_export_mesh_format", "lsd_quick_export_format",
            "lsd_smart_material_type", "lsd_material_transparency",
            "lsd_tex_pos", "lsd_tex_rot", "lsd_tex_scale",
            "lsd_hook_placement_mode", "lsd_camera_preset", "lsd_anchor_initial_size", "lsd_anchor_auto_size",
            "lsd_show_collisions", "lsd_dim_font_name", "lsd_dim_font_bold", "lsd_dim_font_italic",
            "lsd_dim_text_offset", "lsd_scale_mode", "lsd_scale_pivot", "lsd_scale_realtime",
            "lsd_dimensions_master"
        ]
        # Add order props
        prop_names = [
            "lsd_order_ai_factory", "lsd_order_parts", "lsd_order_architectural", "lsd_order_vehicle",
            "lsd_order_electronics", "lsd_order_procedural", "lsd_order_dimensions", "lsd_order_materials",
            "lsd_order_lighting", "lsd_order_kinematics", "lsd_order_physics",
            "lsd_order_transmission", "lsd_order_assets", "lsd_order_export", "lsd_order_preferences"
        ]
        all_scene_props += prop_names

        

        for prop in all_scene_props:

            if hasattr(bpy.types.Scene, prop):

                delattr(bpy.types.Scene, prop)

        

        # 2. Clean up Object and Bone Pointers
        if hasattr(bpy.types.Object, "lsd_pg_mech_props"):

            del bpy.types.Object.lsd_pg_mech_props

        if hasattr(bpy.types.PoseBone, "lsd_pg_kinematic_props"):

            del bpy.types.PoseBone.lsd_pg_kinematic_props

            

    except Exception as e:

        print(f"Error during LSD property cleanup: {e}")

        

    # 3. Unregister classes in reverse order
    for cls in reversed(CLASSES):

        try:

            bpy.utils.unregister_class(cls)

        except Exception:

            pass
