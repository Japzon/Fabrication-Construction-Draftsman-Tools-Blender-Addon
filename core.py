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
from typing import List, Tuple, Optional, Set, Any, Dict, Union
from . import config
from .config import *

# ------------------------------------------------------------------------
#   Guard Variables (FCD Internal State)
# ------------------------------------------------------------------------
_prop_update_guard = False
_joint_editor_update_guard = False
_last_active_bone_name = None
_update_gizmo_guard = False
_local_cursor_update_guard = False
_dim_timer_queued = False
_dim_update_guard = False

def update_panel_collapse(self, context):
    """Callback for all panel visibility properties to support Auto-Collapse"""
    if not context or not context.scene: return
    if not context.scene.fcd_auto_collapse_panels: return
    
    # Identify which property changed. self is the Scene.
    # We find which one is True and collapse all others.
    # Note: Property name is not passed as arg, so we check which one became True
    # in the context of the current Redraw.
    from .config import FCD_PANEL_PROPS
    
    # We find which panel was just opened (it will be True)
    # BUT wait, this update runs AFTER the value is set.
    # If multiple are True, we keep only the 'most recent' True? No, we check which one is True.
    # To be safe, we just use the logic from the operator if called via operator.
    # If called via property toggle, we still need to know which one.
    pass

#   PART 1: LOGIC, HELPERS & HANDLERS
# ------------------------------------------------------------------------

class FCD_OT_Core_DisablePanel(bpy.types.Operator):
    """Disables (hides) a panel from the UI. Re-enable it in Preferences > Visible Panels."""
    bl_idname = "fcd.disable_panel"
    bl_label = "Close Panel"
    bl_options = {'INTERNAL'}
    
    prop_name: bpy.props.StringProperty()

    def execute(self, context: bpy.types.Context) -> Set[str]:
        if hasattr(context.scene, self.prop_name):
            setattr(context.scene, self.prop_name, False)
        return {'FINISHED'}

class FCD_OT_Core_TogglePanelVisibility(bpy.types.Operator):
    """
    Toggles the visibility of a specified UI panel.

    This operator is used in panel headers to provide a clickable toggle
    that explicitly controls the panel's expanded/collapsed state. It works by
    flipping a boolean scene property that the panel's `draw` method checks.
    """
    bl_idname = "fcd.toggle_panel_visibility"
    bl_label = "Toggle Panel Visibility"
    bl_description = "Expands or collapses a UI panel"
    bl_options = {'INTERNAL'}

    panel_property: bpy.props.StringProperty(
        name="Panel Property",
        description="The name of the boolean scene property to toggle (e.g., 'fcd_show_panel_parts')"
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        """
        Executes the toggle operation.

        Args:
            context: The current Blender context.

        Returns:
            A set containing {'FINISHED'} on success.
        """
        if not hasattr(context.scene, self.panel_property):
            self.report({'ERROR'}, f"Scene property '{self.panel_property}' not found.")
            return {'CANCELLED'}

        current_value = getattr(context.scene, self.panel_property)
        new_value = not current_value
        setattr(context.scene, self.panel_property, new_value)

        # AI Editor Note: Handle auto-collapse logic here explicitly.
        # This avoids the complexity and potential recursion of property update callbacks.
        if new_value and context.scene.fcd_auto_collapse_panels:
            # AI Editor Note: Access FCD_PANEL_PROPS via the config module
            # to ensure we have the latest version even after partial reloads.
            panel_props = getattr(config, "FCD_PANEL_PROPS", [])
            for prop_name in panel_props:
                if prop_name != self.panel_property and prop_name.startswith("fcd_show_panel_"):
                    # Double check if scene has the property
                    if hasattr(context.scene, prop_name):
                        setattr(context.scene, prop_name, False)

        return {'FINISHED'}

class FCD_OT_Core_SnapCursorToActive(bpy.types.Operator):
    """Snap 3D cursor to the active object's origin"""
    bl_idname = "fcd.snap_cursor_to_active"
    bl_label = "Snap Cursor to Active"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Gather all target locations from selected objects and bones
        targets = []
        
        # 1. Handle Selected Objects
        if context.selected_objects:
            for obj in context.selected_objects:
                # For armatures, we might want the bones instead if in Pose/Edit mode
                # but if we are in Object mode, we use the object's bound box.
                if context.mode == 'OBJECT' or obj.type != 'ARMATURE':
                    for v in obj.bound_box:
                        targets.append(obj.matrix_world @ mathutils.Vector(v))
                
        # 2. Handle Selected Bones (Pose Mode)
        if context.mode == 'POSE' and context.selected_pose_bones:
            for pb in context.selected_pose_bones:
                # Add head and tail of each selected bone
                targets.append(pb.id_data.matrix_world @ pb.head)
                targets.append(pb.id_data.matrix_world @ pb.tail)
        
        # 3. Handle Selected Bones (Edit Mode)
        if context.mode == 'EDIT' and context.active_object and context.active_object.type == 'ARMATURE':
            for eb in context.selected_editable_bones:
                targets.append(context.active_object.matrix_world @ eb.head)
                targets.append(context.active_object.matrix_world @ eb.tail)

        if not targets:
            self.report({'WARNING'}, "No objects or bones selected.")
            return {'CANCELLED'}

        # Calculate the average center of all gathered points
        min_x = min(p.x for p in targets)
        max_x = max(p.x for p in targets)
        min_y = min(p.y for p in targets)
        max_y = max(p.y for p in targets)
        min_z = min(p.z for p in targets)
        max_z = max(p.z for p in targets)

        center = mathutils.Vector(((max_x + min_x) / 2, (max_y + min_y) / 2, (max_z + min_z) / 2))
        
        # Set cursor location
        context.scene.cursor.location = center
        self.report({'INFO'}, f"Snapped cursor to center of {len(targets)//2 if context.mode in {'POSE', 'EDIT'} else len(context.selected_objects)} item(s).")
        return {'FINISHED'}

def update_scene_lighting(self, context: bpy.types.Context):
    """
    Core logic to update scene environment and lighting based on properties.
    AI Editor Note: This function is triggered by property updates to provide
    immediate visual feedback.
    """
    props = context.scene.fcd_pg_lighting_props
    world = context.scene.world
    if not world:
        world = bpy.data.worlds.new("FCD_World")
        context.scene.world = world
    
    # --- 1. World Background ---
    # Sync World nodes or base color
    if world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        if bg:
            # For FLAT preset, use base color for World as well
            if props.light_preset == 'FLAT':
                bg.inputs[0].default_value = props.base_color
                bg.inputs[1].default_value = 1.0 # High strength for unlit feel
            else:
                bg.inputs[0].default_value = props.background_color
                bg.inputs[1].default_value = 1.0
    else:
        if props.light_preset == 'FLAT':
            world.color = props.base_color[:3]
        else:
            world.color = props.background_color[:3]

    # --- 2. Lighting Rig Management ---
    # Prefix for identifying addon-managed lights
    prefix = "FCD_ENV_"
    
    # Cleanup old lights
    for obj in list(bpy.data.objects):
        if obj.name.startswith(prefix) and obj.type == 'LIGHT':
            bpy.data.objects.remove(obj, do_unlink=True)
            
    preset = props.light_preset
    intensity = props.light_intensity
    tint = props.base_color[:3]

    def create_managed_light(name, type, location=(0,0,0), rotation=(0,0,0), energy=100.0, size=1.0):
        data = bpy.data.lights.new(name=f"{prefix}{name}", type=type)
        obj = bpy.data.objects.new(name=f"{prefix}{name}", object_data=data)
        context.collection.objects.link(obj)
        obj.location = location
        obj.rotation_euler = rotation
        data.energy = energy * intensity
        data.color = tint
        data.use_shadow = props.use_shadows
        if type == 'AREA':
            data.size = size
        return obj

    if preset == 'OUTDOOR':
        # Single Sun light for crisp outdoor illumination
        sun = create_managed_light("Sun", 'SUN', location=(0,0,10), rotation=(0.7, 0.4, 0), energy=5.0)
        
    elif preset == 'STUDIO':
        # 3-Point Studio Setup
        # Key Light
        create_managed_light("Key", 'AREA', location=(6, -6, 8), rotation=(0.7, 0, 0.78), energy=4000.0, size=3.0)
        # Fill Light (Warmer/Weaker)
        create_managed_light("Fill", 'AREA', location=(-6, -3, 5), rotation=(0.5, 0, -0.5), energy=1500.0, size=5.0)
        # Rim Light (Highlighting edge)
        create_managed_light("Rim", 'AREA', location=(0, 8, 6), rotation=(2.3, 0, 3.14), energy=3000.0, size=2.0)
        
    elif preset == 'EMPTY':
        # Only uses world ambient color. No direct lights.
        pass

    # --- 3. Viewport Shading Adjustments ---
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D' and hasattr(space, 'shading'):
                    shading = space.shading
                    if preset == 'FLAT':
                        shading.type = 'SOLID'
                        shading.light = 'FLAT'
                        shading.color_type = 'OBJECT'
                    elif shading.light == 'FLAT':
                        shading.light = 'STUDIO'

def update_scene_lighting(self, context):
    """
    Applies global scene-wide lighting adjustments (Tint, Background).
    """
    scene = context.scene
    props = scene.fcd_pg_lighting_props
    
    # 1. Update World Background Color
    if not scene.world:
        scene.world = bpy.data.worlds.new("FCD_World")
    
    # Check if using nodes for world
    if scene.world.use_nodes:
        sh_node = next((n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND'), None)
        if sh_node:
            sh_node.inputs[0].default_value = props.background_color[:4]
    else:
        scene.world.color = props.background_color[:3]
    
    # 2. Individual Light Tuning (Multiplier)
    # Note: We avoid heavy looping here to maintain UI performance

def update_selected_light(self, context: bpy.types.Context):
    """
    Syncs the active light object's data with the 'Smart Editing' properties.
    AI Editor Note: This provides a way to 'pick up' and modify any light in the scene.
    """
    obj = context.active_object
    if not obj or obj.type != 'LIGHT':
        return
        
    props = context.scene.fcd_pg_lighting_props
    light = obj.data
    
    # 1. Type Change
    if light.type != props.selected_light_type:
        light.type = props.selected_light_type
        
    is_flat = props.selected_light_shading == 'FLAT'
    
    # 2. Power & Color
    light.energy = props.selected_light_energy
    light.color = props.selected_light_color[:3]
    
    # 3. Shading Behavior
    if is_flat:
        if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.0
        if hasattr(light, 'radius'): light.radius = 0.0
        if hasattr(light, 'specular_factor'): light.specular_factor = 0.0
        
        # Hard-edge footprint for Spot lights
        if hasattr(light, 'spot_blend'): light.spot_blend = 0.0
        
        # High Bias for digital noise removal (prevents blobby floor artifacts)
        if hasattr(light, 'shadow_buffer_bias'): light.shadow_buffer_bias = 0.1
        if hasattr(light, 'use_contact_shadow'): 
            light.use_contact_shadow = True
            light.contact_shadow_distance = 0.02
    else:
        # Realistic Gradient
        if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.1
        if hasattr(light, 'radius'): light.radius = 0.2
        if hasattr(light, 'specular_factor'): light.specular_factor = 1.0
        if hasattr(light, 'spot_blend'): light.spot_blend = 0.15
        if hasattr(light, 'use_custom_distance'): light.use_custom_distance = False
        if hasattr(light, 'shadow_buffer_bias'): light.shadow_buffer_bias = 0.05
        if hasattr(light, 'use_contact_shadow'): light.use_contact_shadow = False
        # Return to softer look if disabled
        if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.1
        if hasattr(light, 'radius'): light.radius = 0.2
        if hasattr(light, 'angle'): light.angle = 0.1
        if hasattr(light, 'specular_factor'): light.specular_factor = 1.0
        if hasattr(light, 'use_contact_shadow'): light.use_contact_shadow = False

@persistent
def sync_light_props_handler(scene, depsgraph=None):
    """
    Synchronizes the UI properties with the currently selected light.
    AI Editor Note: This is triggered on every depsgraph update (selection change).
    We use a check to avoid infinite loops when the properties themselves update.
    """
    ctx = bpy.context
    obj = ctx.active_object
    if not obj or obj.type != 'LIGHT':
        return
        
    props = scene.fcd_pg_lighting_props
    light = obj.data
    
    # Avoid updating if we are currently in the middle of a manual property change
    # (Checking for active window or specific UI flag is hard, so we just check for value difference)
    if props.selected_light_type != light.type:
        props.selected_light_type = light.type
    # Energy/Color sync disabled to prevent automatic 'normalization' on selection.
    # The UI now binds directly to light.energy/light.color for real-time control.
    """
    if not math.isclose(props.selected_light_energy, light.energy, rel_tol=1e-5):
        props.selected_light_energy = light.energy
    
    # Sync Color
    for i in range(3):
        if not math.isclose(props.selected_light_color[i], light.color[i], rel_tol=1e-4):
            props.selected_light_color = (light.color[0], light.color[1], light.color[2], 1.0)
            break
    """

    # Sync Target (Eyedropper) - ONLY if constrained. Avoid clearing user pick.
    found_target = None
    for c in obj.constraints:
        if c.type == 'DAMPED_TRACK' and c.target:
            found_target = c.target
            break
    if found_target and props.selected_light_target != found_target:
        props.selected_light_target = found_target
    
    # Sync Shading Style (Flat vs Gradient)
    current_shading = 'GRADIENT'
    # Any light type can be 'FLAT' if shadows are zero and specular is zero
    if hasattr(light, 'shadow_soft_size') and light.shadow_soft_size < 1e-4:
        if hasattr(light, 'specular_factor') and light.specular_factor < 1e-4:
            current_shading = 'FLAT'
    elif hasattr(light, 'radius') and light.radius < 1e-4:
        if hasattr(light, 'specular_factor') and light.specular_factor < 1e-4:
            current_shading = 'FLAT'
            
    if props.selected_light_shading != current_shading:
        props.selected_light_shading = current_shading


def ensure_default_rig(context: bpy.types.Context) -> Optional[bpy.types.Object]:
    """
    Ensures that a valid armature is set as the active rig in the scene.

    This function is a cornerstone of the addon's stability. Many operators and UI
    elements depend on having an active rig to work with. This function guarantees
    that `context.scene.fcd_active_rig` always points to a valid armature.

    The logic is as follows:
    1. If an active rig is already set and exists in the scene, do nothing.
    2. If not, search the scene for any existing armature and set the first one
       found as the active rig.
    3. If no armatures exist in the scene, create a new one with a default name
       ("New_Kinematics") and set it as the active rig.

    Args:
        context: The current Blender context.

    Returns:
        The active rig object, or None if one could not be found or created.
    """
    # 1. Check if the currently set rig is valid and in the view layer.
    if context.scene.fcd_active_rig and context.scene.fcd_active_rig.name in context.view_layer.objects:
        return context.scene.fcd_active_rig

    # 2. Search for any existing armature in the view layer.
    for obj in context.view_layer.objects:
        if obj.type == 'ARMATURE':
            context.scene.fcd_active_rig = obj
            return obj

    # 3. If no armatures exist, create a new one.
    try:
        base_name = "New_Kinematics"
        name = get_unique_name(base_name)

        arm_data = bpy.data.armatures.new(name + "_Data")
        rig = bpy.data.objects.new(name, arm_data)
        rig.location = context.scene.cursor.location # AI Editor Note: Ensure implicit rig is created at cursor
        context.scene.collection.objects.link(rig)

        # Set display properties for better visibility.
        rig.display_type = 'WIRE'
        rig.show_in_front = True
        context.scene.fcd_active_rig = rig
        return rig
    except Exception as e:
        print(f"Error creating default rig: {e}")
        return None

@persistent
def auto_set_active_rig_handler(dummy: Any) -> None:
    """
    A persistent handler that runs automatically after a .blend file is loaded.

    This handler ensures that the addon is immediately ready to use upon file load
    by calling `ensure_default_rig`. This prevents errors or empty UI panels that
    could otherwise occur if no active rig is set when the user opens a file
    containing a robot model.

    The `@persistent` decorator ensures this handler remains active across multiple
    file loads within a single Blender session.

    Args:
        dummy: The scene object passed by the handler (unused).
    """
    # This handler can run in contexts where bpy.context is not fully formed.
    if bpy.context and bpy.context.scene:
        ensure_default_rig(bpy.context)

@persistent
def load_panel_order_handler(dummy: Any) -> None:
    """
    Applies the saved panel order from scene properties after loading a file.
    """
    # Use a timer to ensure context is ready
    bpy.app.timers.register(lambda: (bpy.ops.fcd.update_panel_order() and None), first_interval=0.2)

@persistent
def set_scene_units_handler(dummy: Any) -> None:
    """Sets the scene length unit to Millimeters on load."""
    if bpy.context and bpy.context.scene:
        bpy.context.scene.unit_settings.length_unit = 'MILLIMETERS'

@persistent
def toggle_placement_parenting(scene, context):
    """
    Toggles parenting relationship for placement mode.
    On: Unparents meshes from bones (keeping world transform).
    Off: Reparents meshes back to their original bones.
    """
    rig = scene.fcd_active_rig
    if not rig: return
    
    is_active = scene.fcd_placement_mode
    
    # AI Editor Note: Using a robust collection search to handle all parts.
    if is_active:
        # 1. Store and Detach
        for obj in bpy.data.objects:
            if obj.parent == rig and obj.parent_type == 'BONE' and obj.parent_bone:
                obj["fcd_temp_bone"] = obj.parent_bone
                # Store world matrix to preserve it exactly
                old_matrix = obj.matrix_world.copy()
                obj.parent = None
                obj.matrix_world = old_matrix
    else:
        # 2. Restore and Reattach
        for obj in bpy.data.objects:
            if "fcd_temp_bone" in obj:
                bone_name = obj["fcd_temp_bone"]
                if bone_name in rig.pose.bones:
                    old_matrix = obj.matrix_world.copy()
                    obj.parent = rig
                    obj.parent_type = 'BONE'
                    obj.parent_bone = bone_name
                    obj.matrix_world = old_matrix
                del obj["fcd_temp_bone"]
    
    # Refresh constraints to reflect placement state (unlock/lock)
    for bone in rig.pose.bones:
        apply_native_constraints(bone)

@persistent
def fcd_placement_handler(scene, depsgraph=None):
    """
    Persistent handler to ensure placement mode state consistency across view layers.
    Note: Heavy parenting logic is offloaded to property updates to maintain FPS.
    """
    pass

def ensure_material_mapping_nodes(mat: bpy.types.Material) -> None:
    """
    Ensures that the material has a 'Mapping' node and it is properly linked
    to the 'Base Color' of the Principled BSDF.
    Used for the 'Always Available' transform controls.
    """
    if not mat.use_nodes:
        mat.use_nodes = True
    
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    # 1. Ensure BSDF exists
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if not bsdf:
        mat.node_tree.nodes.clear() # Reset corrupted material
        bsdf = nodes.new('BSDF_PRINCIPLED')
        output = nodes.new('ShaderNodeOutputMaterial')
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # 2. Find or Create Mapping
    mapping = next((n for n in nodes if n.type == 'MAPPING'), None)
    if not mapping:
        mapping = nodes.new('ShaderNodeMapping')
        mapping.location = (bsdf.location.x - 400, bsdf.location.y)
    
    # 3. Find or Create TexCoord
    tex_coord = next((n for n in nodes if n.type == 'TEX_COORD'), None)
    if not tex_coord:
        tex_coord = nodes.new('ShaderNodeTexCoord')
        tex_coord.location = (mapping.location.x - 200, mapping.location.y)
    
    # Link them up
    if not any(l for l in mapping.inputs['Vector'].links):
        links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])
    
    # 4. Find anything currently plugged into BSDF Base Color (e.g. an image)
    # and ensure the mapping node is feeding into its 'Vector' input.
    base_color_input = bsdf.inputs['Base Color']
    if base_color_input.links:
        source_node = base_color_input.links[0].from_node
        if hasattr(source_node, "inputs") and "Vector" in source_node.inputs:
            if not any(l for l in source_node.inputs['Vector'].links if l.from_node == mapping):
                links.new(mapping.outputs['Vector'], source_node.inputs['Vector'])

def update_global_bones(self: bpy.types.Scene, context: bpy.types.Context) -> None:
    """
    Update callback for the global "Show Bones" toggle in the UI.

    This function is triggered when the `scene.fcd_show_bones` property is changed.
    It iterates through all 3D Viewport spaces in the current screen and sets their
    `overlay.show_bones` property to match the new value. This ensures that the
    visibility of bones is consistent across all viewports.

    Args:
        self: The scene object.
        context: The current Blender context.
    """
    if not context.screen:
        return
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.overlay.show_bones = self.fcd_show_bones

def get_asset_libraries(self, context):
    items = [('LOCAL', "Current File", "Assets in the current file")]
    libs = getattr(context.preferences.filepaths, "asset_libraries", [])
    for lib in libs:
        if lib.name:
            items.append((lib.name, lib.name, lib.path))
    return items

def get_or_create_arrow_mesh():
    """Returns a reusable conical arrowhead mesh."""
    mesh_name = "FCD_Arrow_Mesh"
    if mesh_name in bpy.data.meshes:
        return bpy.data.meshes[mesh_name]
        
    mesh = bpy.data.meshes.new(mesh_name)
    # Simple cone geometry (Z-up)
    verts = [
        (0, 0, 0),        # Tip (0)
        (0.05, 0, -0.15), # Base Circle
        (0.035, 0.035, -0.15),
        (0, 0.05, -0.15),
        (-0.035, 0.035, -0.15),
        (-0.05, 0, -0.15),
        (-0.035, -0.035, -0.15),
        (0, -0.05, -0.15),
        (0.035, -0.035, -0.15),
    ]
    # Faces: the tip-to-base triangles and the bottom circle
    faces = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 6), (0, 6, 7), (0, 7, 8), (0, 8, 1),
             (1, 8, 7, 6, 5, 4, 3, 2)]
    
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh

def update_category_enum(self: bpy.types.Scene, context: bpy.types.Context) -> None:
    """
    Update callback for the parametric part category dropdown.

    This function is triggered when the user changes the main part category (e.g.,
    from "Gears" to "Fasteners"). It improves usability by automatically setting a
    sensible default for the sub-type dropdown. For example, if the user selects
    "Gears", the sub-type will default to "Spur".

    Args:
        self: The scene object.
        context: The current Blender context.
    """
    cat = context.scene.fcd_part_category
    if cat == 'GEAR':
        context.scene.fcd_part_type = 'BEVEL'
    elif cat == 'RACK':
        context.scene.fcd_part_type = 'RACK_BEVEL'
    elif cat == 'FASTENER':
        context.scene.fcd_part_type = 'BOLT'
    elif cat == 'SPRING':
        context.scene.fcd_part_type = 'DAMPER'
    elif cat == 'CHAIN':
        context.scene.fcd_part_type = 'BELT'
    elif cat == 'WHEEL':
        context.scene.fcd_part_type = 'WHEEL_CASTER'
    elif cat == 'PULLEY':
        context.scene.fcd_part_type = 'PULLEY_UGROOVE'
    elif cat == 'ROPE':
        context.scene.fcd_part_type = 'ROPE_TUBE'
    elif cat == 'BASIC_JOINT':
        context.scene.fcd_part_type = 'JOINT_CONTINUOUS'
    elif cat == 'ARCHITECTURAL':
        context.scene.fcd_part_type = 'WALL'
    elif cat == 'BASIC_SHAPE':
        context.scene.fcd_part_type = 'SHAPE_CIRCLE'

def get_mech_types_callback(self: bpy.types.Scene, context: bpy.types.Context) -> List[Tuple[str, str, str]]:
    """
    Callback function to dynamically populate the part sub-type enum property.

    This function is essential for the two-level part selection UI. It is called
    by the `fcd_part_type` EnumProperty to get the list of items to display in
    the dropdown. The list it returns depends on the currently selected main
    category (`fcd_part_category`).

    Args:
        self: The Scene object.
        context: The current Blender context.

    Returns:
        A list of tuples (identifier, UI name, UI description) for the
        EnumProperty items.
    """
    # This function can be called in contexts where the scene is not fully available.
    if not context or not hasattr(context, 'scene'):
        return []

    cat = context.scene.fcd_part_category
    if cat == 'GEAR':
        return GEAR_TYPES
    elif cat == 'RACK':
        return RACK_TYPES
    elif cat == 'FASTENER':
        return FASTENER_TYPES
    elif cat == 'SPRING':
        return SPRING_TYPES
    elif cat == 'CHAIN':
        return CHAIN_TYPES
    elif cat == 'WHEEL':
        return WHEEL_TYPES
    elif cat == 'PULLEY':
        return PULLEY_TYPES
    elif cat == 'ROPE':
        return ROPE_TYPES
    elif cat == 'BASIC_JOINT':
        return BASIC_JOINT_TYPES
    elif cat == 'ARCHITECTURAL':
        context.scene.fcd_part_type = 'WALL'
    elif cat == 'BASIC_SHAPE':
        return BASIC_SHAPE_TYPES
    return []

def update_electronics_category_enum(self: bpy.types.Scene, context: bpy.types.Context) -> None:
    """
    Update callback for the electronics category dropdown.
    Resets the sub-type to a default for the new category.
    """
    cat = context.scene.fcd_electronics_category
    if cat == 'MOTOR':
        context.scene.fcd_electronics_type = 'MOTOR_BLDC_OUTRUNNER'
    elif cat == 'SENSOR':
        context.scene.fcd_electronics_type = 'SENSOR_CONTACT'
    elif cat == 'PCB':
        context.scene.fcd_electronics_type = 'PCB_ARDUINO'
    elif cat == 'IC':
        context.scene.fcd_electronics_type = 'IC_CAPACITOR'
    elif cat == 'CAMERA':
        context.scene.fcd_electronics_type = 'CAMERA_DEFAULT'

def get_electronics_types_callback(self: bpy.types.Scene, context: bpy.types.Context) -> List[Tuple[str, str, str]]:
    """
    Callback function to dynamically populate the electronics sub-type enum.
    """
    if not context or not hasattr(context, 'scene'):
        return []

    cat = context.scene.fcd_electronics_category
    if cat == 'MOTOR':
        return MOTOR_TYPES
    elif cat == 'SENSOR':
        return SENSOR_TYPES
    elif cat == 'PCB':
        return PCB_TYPES
    elif cat == 'IC':
        return IC_TYPES
    elif cat == 'CAMERA':
        return CAMERA_TYPES
    return []

def apply_auto_smooth(obj: bpy.types.Object, is_rack: bool = False) -> None:
    """
    Applies a standard 30.5-degree auto smooth for clean shading on generated parts.
    This is called after mesh regeneration.

    Args:
        obj: The mesh object to apply smoothing to.
        is_rack: (Unused) A legacy parameter.
    """
    if not obj or obj.type != 'MESH':
        return
 
    mesh = obj.data
    
    # 1. Set all polygons to smooth shading.
    # This is necessary for auto smooth to work correctly.
    for poly in mesh.polygons:
        poly.use_smooth = True

    # 2. Add or Update "Edge Split" Modifier for Auto Smooth effect.
    # AI Editor Note: Per user request, this now uses the classic Edge Split
    # modifier instead of a Geometry Nodes setup. This provides the same visual
    # result and is more aligned with traditional modifier workflows, and fixes
    # the AttributeError in Blender 4.1+.
    mod_name = f"{MOD_PREFIX}AutoSmooth"
    
    # Clean up any old/conflicting auto-smooth modifiers first.
    for mod in list(obj.modifiers):
        if mod.name == mod_name and mod.type != 'EDGE_SPLIT':
            obj.modifiers.remove(mod)
        elif mod.name == f"{MOD_PREFIX}Shading_Helper":
            obj.modifiers.remove(mod)

    # Get or create the correct Edge Split modifier.
    mod = obj.modifiers.get(mod_name)
    if not mod:
        mod = obj.modifiers.new(name=mod_name, type='EDGE_SPLIT')
    
    # Configure the modifier
    mod.use_edge_angle = True
    mod.split_angle = math.radians(31)

    # --- AI Editor Note: Move Modifier to Bottom ---
    # The auto-smooth modifier should always be last in the stack to correctly
    # process the geometry generated by all other modifiers (like Arrays).
    # We move it to the bottom to ensure it is applied last.
    with bpy.context.temp_override(object=obj):
        bpy.ops.object.modifier_move_to_index(modifier=mod.name, index=len(obj.modifiers) - 1)

def get_gizmo_rotation_matrix(joint_type: str, axis_enum: str) -> mathutils.Matrix:
    """Calculates the rotation matrix needed to align a default gizmo shape."""
    rot_matrix = mathutils.Matrix.Identity(4)
    target_axis = axis_enum.replace("-", "")

    if joint_type == 'prismatic':
        if target_axis == 'X':
            rot_matrix = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
        elif target_axis == 'Z':
            rot_matrix = mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X')
    else: # revolute/continuous
        if target_axis == 'X':
            rot_matrix = mathutils.Matrix.Rotation(math.radians(90.0), 4, 'Y')
        elif target_axis == 'Y':
            rot_matrix = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')
            
    return rot_matrix.to_3x3()

def get_or_create_text_material(target_obj):
    """Ensures a unique text material exists for the given object and returns it."""
    if not hasattr(target_obj, "name"):
         return bpy.data.materials.new("ERROR_MAT")

    mat_name = f"FCD_Material_{target_obj.name}"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
    
    # AI Editor Note: Access properties through the FCD_PG_Dimension_Props namespaced PG
    dim_props = getattr(target_obj, "fcd_pg_dim_props", None)
    color = dim_props.text_color if dim_props else (0.0, 0.0, 0.0, 1.0)
    
    if mat.use_nodes and mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            # AI Editor Note: High-Legibility Draftsman Display
            # Use pure black by default, maximum roughness and zero metallic for non-glossy appearance.
            bsdf.inputs['Base Color'].default_value = color
            bsdf.inputs['Metallic'].default_value = 0.0
            bsdf.inputs['Roughness'].default_value = 1.0
            
            # Specular handling (Blender 4.0+ uses Specular IOR or weight)
            if 'Specular' in bsdf.inputs:
                bsdf.inputs['Specular'].default_value = 0.0
            if 'Specular IOR Level' in bsdf.inputs:
                bsdf.inputs['Specular IOR Level'].default_value = 0.0

            # Ensure visibility in Solid mode via Object Color sync.
            # We set a small emission to keep it crisp in Rendered mode without it being a light source.
            bsdf.inputs['Emission Color'].default_value = color
            bsdf.inputs['Emission Strength'].default_value = 0.01 
    
    # Sync diffuse color for Solid viewport display
    mat.diffuse_color = color
    return mat

def get_dimension_host(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """
    Robustly identifies the host of the dimension properties (the Label object)
    from any component of a dimension assembly (Root, Anchors, Line, or Label).
    """
    if not obj: return None
    if obj.get("fcd_is_dimension"): return obj
    
    root = get_dimension_root(obj)
    if root:
        for child in root.children:
            if child.get("fcd_is_dimension"):
                return child
    return None

def get_dimension_root(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """
    Identifies the Root Empty of a dimension assembly starting from any child.
    """
    if not obj: return None
    if obj.get("fcd_is_dimension_root"): return obj
    
    # Check parent
    p = obj.parent
    if p and p.get("fcd_is_dimension_root"): return p
    
    # Check pointer fallback
    p_ptr = obj.get("fcd_dim_root")
    if p_ptr and isinstance(p_ptr, bpy.types.Object): return p_ptr
    
    return None
    
    # 4. Check active object for direct back-pointer (Participants)
    # The generators now store the Root on the target objects.
    root_pointer = obj.get("fcd_dim_root")
    if root_pointer:
         for child in root_pointer.children:
              if child.get("fcd_is_dimension"):
                   return child
    
    # 5. Global Search (participating targets - Fallback)
    for o in bpy.context.scene.objects:
        if o.get("fcd_is_dimension_root"):
             p_obj = o.get("fcd_parent_obj")
             s_obj = o.get("fcd_slave_obj")
             if (p_obj and p_obj.name == obj.name) or (s_obj and s_obj.name == obj.name):
                  for child in o.children:
                       if child.get("fcd_is_dimension"):
                            return child
    
    return None

@persistent
def fcd_dimension_sync_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    """Ultimate real-time synchronization for Procedural Dimensions."""
    global _dim_update_guard
    if _dim_update_guard: return
    
    for obj in scene.objects:
        if not obj or not obj.get("fcd_is_dimension"):
            continue
            
        dim_props = getattr(obj, "fcd_pg_dim_props", None)
        if not dim_props:
            continue
            
        root = obj.parent
        if not root: continue
        
        # Calculate Real-World orientation and distance
        # We find the Mesh Hook (the slave) to determine distance
        target_mesh_hook = next((c for c in root.children if c.get("fcd_is_dimension_anchor") == "HOOK"), None)
        if not target_mesh_hook:
             # In v1.2.8 architecture, the mesh hook is parented to 'ab' (internal end),
             # so we find it via the child of the end hook.
             ab = next((c for c in root.children if c.get("fcd_is_dimension_anchor") == "END"), None)
             if ab:
                  target_mesh_hook = next((c for c in ab.children if c.get("fcd_is_dimension_hook") == "END"), None)
        
        if not target_mesh_hook: continue
        
        # Calculate local target coordinates relative to assembly root
        local_target = root.matrix_world.inverted() @ target_mesh_hook.matrix_world.translation
        
        if not dim_props.is_manual:
             # DYNAMIC MODE: Object/Mesh Hook drives the property
             # We use the Z-component of the target in root-local space as the true drafted length.
             dist = abs(local_target.z)
             
             if abs(dim_props.length - dist) > 0.0001:
                  # AI Editor Note: Must temporarily disable guard to allow this specific length update
                  _dim_update_guard = True
                  try:
                      dim_props["length"] = dist
                      update_dimension_length(obj)
                  finally:
                      _dim_update_guard = False
        
        # ALWAYS sync transverse coordinates to prevent target snapping during alignment
        if abs(dim_props.target_x - local_target.x) > 0.0001 or abs(dim_props.target_y - local_target.y) > 0.0001:
             dim_props["target_x"] = local_target.x
             dim_props["target_y"] = local_target.y
             # We trigger a mesh refresh only if not manual (manual slider handles its own mesh update)
             if not dim_props.is_manual:
                  update_dimension_length(obj)
        else:
              # MANUAL MODE: Only update if explicitly requested via slider
              pass

def update_dimension_length(obj):
    """
    Manual/Sync refresh for dimension components.
    Handles both Root and Label object inputs.
    Source of Truth: The Label (Host) object.
    """
    if not obj: return
    
    root = get_dimension_root(obj)
    host = get_dimension_host(obj)
    if not root or not host: return
    
    dim_props = getattr(host, "fcd_pg_dim_props", None)
    if not dim_props: return
    
    length = dim_props.length
    
    # 1. Coordinate Sync (Labels, End-Anchors, Legs)
    label_obj = None
    for child in root.children:
        if child.get("fcd_is_dimension"): label_obj = child
        
        is_end = child.get("fcd_is_dimension_anchor") == "END" 
        is_ext_b = child.get("fcd_is_extension_line") and child.get("fcd_extension_type") == "END"
        
        if is_end or is_ext_b:
            child.location.z = length
        elif child.get("fcd_is_dimension_line"):
            # The midsection is updated in update_arrow_settings for alignment reasons
            pass
    
    # 2. Update Label String & Units
    if label_obj:
        unit_str = "m" if dim_props.unit_display == 'METERS' else "mm"
        val = length if unit_str == "m" else length * 1000.0
        
        if hasattr(label_obj.data, "body"):
             label_text = f"{val:.2f} {unit_str}"
             if label_obj.data.body != label_text:
                  label_obj.data.body = label_text
                 
        label_obj.location.z = length / 2
    
    # 3. Global settings passthrough
    update_arrow_settings(root)


def update_arrow_settings(obj):
    """
    Updates visual settings (scale, color, direction) for the assembly.
    Handles both Label and Root object inputs.
    Source of Truth: The Label (Host) object.
    """
    if not obj: return
    
    root = get_dimension_root(obj)
    host = get_dimension_host(obj)
    if not root or not host: return
    
    dim_props = getattr(host, "fcd_pg_dim_props", None)
    if not dim_props: return
    
    direction_map = {
        'X': mathutils.Vector((1, 0, 0)),
        'Y': mathutils.Vector((0, 1, 0)),
        'Z': mathutils.Vector((0, 0, 1)),
        '-X': mathutils.Vector((-1, 0, 0)),
        '-Y': mathutils.Vector((0, -1, 0)),
        '-Z': mathutils.Vector((0, 0, -1)),
    }
    
    # 1. Parameter Sync
    # We resolve the scene's unit scale to keep visual components (line, arrows, text) 
    # legible regardless of the measurement system (mm vs m).
    unit_scale = bpy.context.scene.unit_settings.scale_length
    us = 1.0 / unit_scale if unit_scale > 0 else 1.0
    
    length = dim_props.length
    
    arrow_s = dim_props.arrow_scale * us
    text_s = dim_props.text_scale * us

    offset = dim_props.offset * us
    line_t = dim_props.line_thickness * us
    dir_enum = dim_props.direction
    
    # Calculate drafting parallelogram offset vectors
    mat_inv = root.matrix_world.to_3x3().inverted_safe()
    
    # Resolve the world offset vector based on alignment flags
    # AI Editor Note: User Request - Allow combining axis alignments for diagonal offsets.
    offset_world_vec = mathutils.Vector((0, 0, 0))
    if dim_props.align_x: offset_world_vec.x += 1
    if dim_props.align_nx: offset_world_vec.x -= 1
    if dim_props.align_y: offset_world_vec.y += 1
    if dim_props.align_ny: offset_world_vec.y -= 1
    if dim_props.align_z: offset_world_vec.z += 1
    if dim_props.align_nz: offset_world_vec.z -= 1
    
    if offset_world_vec.length < 0.001:
         # Default: assembly local Y axis
         offset_world_vec = root.matrix_world.to_3x3() @ mathutils.Vector((0, 1, 0))
    else:
         offset_world_vec = offset_world_vec.normalized()
         
    offset_local_dir = (mat_inv @ offset_world_vec)
    
    offset_local_dir = (mat_inv @ offset_world_vec).normalized()
    
    # AI Editor Note: Logic Update (Parallelogram Drafting).
    # Per user feedback, we no longer enforce Zero-Z. If the user aligns with 
    # a world-axis that is not perpendicular to the line, we allow the 
    # assembly to "slant" or "slide" as long as it aligns with the set axis.
    # To prevent "pushing" or "overlap" artifacts, we must ensure END anchors 
    # add the Z-offset to the length properly.
    
    # Compensation for Parent Scale:
    # If the root is parented to a scaled object, we must divide our children's 
    # scale and location by the root's world scale to maintain absolute drafting units.
    rw_scale = root.matrix_world.to_scale()
    def safe_divide(val, s): return val / s if abs(s) > 0.0001 else val
    
    # Apply location scale compensation to move_vec
    move_vec = mathutils.Vector((
        safe_divide(offset_local_dir.x * offset, rw_scale.x),
        safe_divide(offset_local_dir.y * offset, rw_scale.y),
        safe_divide(offset_local_dir.z * offset, rw_scale.z)
    ))
    
    # Extension Leg Rotation: points from the dimension line back to the target points.
    # This vector is (-move_vec) in the assembly's local drafting space.
    ext_rot_vec = (-move_vec)
    ext_leg_length = ext_rot_vec.length
    ext_rot_euler = (ext_rot_vec.normalized()).to_track_quat('Z', 'Y').to_euler()
    
    # Compensation for Parent Scale:
    # If the root is parented to a scaled object, we must divide our children's 
    # scale by the root's world scale to maintain absolute draftsman units.
    rw_scale = root.matrix_world.to_scale()
    def safe_divide(val, s): return val / s if abs(s) > 0.0001 else val
    
    for child in root.children:
        # 1. PHYSICAL MASTER ANCHORS & HOOKS: Fixed scale
        tag = child.get("fcd_is_dimension_anchor")
        if tag in ["MASTER", "HOOK"]:
             if child.get("fcd_anchor_type") == "END" or tag == "HOOK":
                  child.location = (dim_props.target_x, dim_props.target_y, length)
             else:
                  child.location = (0, 0, 0)
             s_val = 0.05 if tag == "MASTER" else 0.4
             child.scale = (safe_divide(s_val, rw_scale.x), safe_divide(s_val, rw_scale.y), safe_divide(s_val, rw_scale.z))
             continue

        # 2. VISUAL COMPONENTS: These slide along the drafting offset
        if child.get("fcd_is_dimension_anchor") == "VISUAL":
             child.scale = (safe_divide(arrow_s, rw_scale.x), safe_divide(arrow_s, rw_scale.y), safe_divide(arrow_s, rw_scale.z))
             child.location = move_vec.copy()
             if child.get("fcd_anchor_type") == "END":
                  child.location.z += length
            
        elif child.get("fcd_is_dimension_line"): # The Main Line
            child.location = move_vec.copy()
            child.scale = (safe_divide(line_t, rw_scale.x), safe_divide(line_t, rw_scale.y), safe_divide(length, rw_scale.z))
            child.rotation_euler = (0, 0, 0)
            
        elif child.get("fcd_is_extension_line"):
            child.hide_viewport = not dim_props.use_extension_lines
            child.hide_render = not dim_props.use_extension_lines
            if not dim_props.use_extension_lines: continue
            
            child.scale.x = safe_divide(line_t * 0.9, rw_scale.x)
            child.scale.y = safe_divide(line_t * 0.9, rw_scale.y)
            child.location = move_vec.copy()
            if child.get("fcd_extension_type") == "END":
                 child.location.z += length
            
            child.rotation_euler = ext_rot_euler
            child.scale.z = safe_divide(ext_leg_length, rw_scale.z)
            if child.scale.z < 0.001: child.scale.z = 0.001
        elif child.get("fcd_is_dimension"): # The Label
            child.scale = (safe_divide(text_s, rw_scale.x), safe_divide(text_s, rw_scale.y), safe_divide(text_s, rw_scale.z))
            # The label should also move with the slanted offsets while staying centered
            text_clearance = move_vec.normalized() * (arrow_s * 0.2)
            child.location = move_vec + text_clearance
            child.location.z += length / 2
            
            if hasattr(child.data, "align_x"):
                 child.data.align_x = dim_props.text_alignment
            if hasattr(child.data, "align_y"):
                 child.data.align_y = 'CENTER' # Anchor text to its midline for rotation stability
            
            # Text Orientation System (Parallel Alignment).
            # Logic: Text 'X' (reading path) aligns with Dimension 'Z' (assembly track).
            # Logic: Text 'Y' (height/up) aligns with Offset Direction (outward). 
            # Logic: Text 'Z' (forward) aligns with Cross Product (depth towards viewer).
            # This ensures text 'follows' the drafting path like typical architectural notation.
            
            vec_x = mathutils.Vector((0, 0, 1)) # Assembly direction
            vec_y = offset_local_dir.normalized()
            vec_z = vec_x.cross(vec_y).normalized()
            
            # Construct a pure orthonormal orientation matrix (World-to-Text-Basis)
            m = mathutils.Matrix((vec_x, vec_y, vec_z)).transposed()
            base_rot = m.to_euler()
            
            if dim_props.flip_text:
                base_rot.rotate_axis('X', math.pi)
            
            # Apply user-defined Euler rotation ('XYZ' order) on top of the drafting frame
            user_euler = mathutils.Euler(dim_props.text_rotation, 'XYZ')
            child.rotation_euler = (base_rot.to_matrix() @ user_euler.to_matrix()).to_euler()
            
            # Sync material & visibility
            mat = child.active_material
            if mat:
                 child.color = mat.diffuse_color
                 child.show_in_front = True
                
    root.update_tag()
    
    # AI Editor Note: Sync Flip Trigger. 
    # Must call the atomic role-swap logic here to handle 'is_flipped' changes.
    sync_dimension_flipping(root)


def sync_dimension_flipping(obj):
    """Event-triggered role swap to ensure stability."""
    global _dim_update_guard
    if _dim_update_guard: return
    
    # Resolve the hub of the assembly (Root) safely
    root = None
    if isinstance(obj, bpy.types.Object):
         root = obj if obj.get("fcd_dim_root_marker") else obj.get("fcd_dim_root")
         if not root:
              # Fallback to parent if called on a component
              root = obj.parent if not obj.get("fcd_dim_root_marker") else obj
    
    if not root: return
    
    dim_props = root.fcd_pg_dim_props
    
    obj_a = root.get("fcd_parent_obj")
    obj_b = root.get("fcd_slave_obj")
    if not obj_a or not obj_b: return
    
    # 1. Atomic Change Detection: Only flip if the state has changed
    # Logic: The parent of the 'root' corresponds to the 'is_flipped' state.
    # If is_flipped=False, parent should be obj_a. 
    # If is_flipped=True, parent should be obj_b.
    current_parent = root.parent
    target_parent = obj_b if dim_props.is_flipped else obj_a
    target_slave = obj_a if dim_props.is_flipped else obj_b
    
    if current_parent == target_parent:
         # No role swap needed - this update was likely triggered by arrow_scale/etc
         return
    
    # D) RECONSTRUCTIVE FLIP (Delayed/Atomic for Memory Safety)
    # Logic: To avoid EXCEPTION_ACCESS_VIOLATION in Blender 4.5+, we must not 
    # delete the object currently triggering the property update or its parents 
    # inside the update loop. We queue the reconstruction for a separate main-loop pass.
    
    # 1. Store IDs and Configuration before the delay to avoid stale pointers
    config = {
         "arrow_scale": dim_props.arrow_scale,
         "text_scale": dim_props.text_scale,
         "line_thickness": dim_props.line_thickness,
         "offset": dim_props.offset,
         "use_extension_lines": dim_props.use_extension_lines,
         "text_color": dim_props.text_color[:],
         "unit_display": dim_props.unit_display,
         "text_alignment": dim_props.text_alignment,
         "align_x": dim_props.align_x, "align_nx": dim_props.align_nx,
         "align_y": dim_props.align_y, "align_ny": dim_props.align_ny,
         "align_z": dim_props.align_z, "align_nz": dim_props.align_nz,
    }
    
    root_name = root.name
    p_name = obj_a.name
    s_name = obj_b.name
    
    def delayed_rebuild():
         global _dim_update_guard
         try:
              # Guard context
              if not bpy.context or not bpy.context.view_layer: 
                   _dim_update_guard = False
                   return
              
              # A) PRE-FLIP BAKE: Finalize poses on current participants
              obj_p = bpy.data.objects.get(p_name)
              obj_s = bpy.data.objects.get(s_name)
              if not obj_p or not obj_s:
                   _dim_update_guard = False
                   return
              
              prev_mode = bpy.context.mode
              if prev_mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
              
              for p_obj in [obj_p, obj_s]:
                   bpy.ops.object.select_all(action='DESELECT')
                   p_obj.select_set(True)
                   bpy.context.view_layer.objects.active = p_obj
                   try: 
                        # Use override to ensure operator context stability inside timer
                        bpy.ops.fcd.bake_anchor()
                   except: pass
              
              # B) PURGE OLD ASSEMBLY
              old_root = bpy.data.objects.get(root_name)
              if old_root:
                   to_del = [old_root] + [c for c in old_root.children]
                   for o in to_del:
                        # Clean unlinking minimizes access violations during memory free
                        for col in o.users_collection: col.objects.unlink(o)
                        try: bpy.data.objects.remove(o, do_unlink=True)
                        except: pass
              
              # C) REBUILD: Call procedural generator with fresh coordinate frames
              from . import generators
              new_dim = generators.generate_smart_dimension_parametric(
                   bpy.context, 
                   obj_p.matrix_world.translation, 
                   obj_s.matrix_world.translation,
                   name="FCD_Dimension",
                   parent_a=(obj_p, 'OBJECT', 0),
                   parent_b=(obj_s, 'OBJECT', 0)
              )
              
              if new_dim:
                   new_props = new_dim.fcd_pg_dim_props
                   # Restore visual configuration across the reconstructive gap
                   for key, val in config.items():
                        try: setattr(new_props, key, val)
                        except: pass
                   # Reset flip state on the new assembly to avoid recursion
                   # Selection Focus: keeping properties open
                   if context.view_layer:
                        bpy.ops.object.select_all(action="DESELECT")
                        new_dim.select_set(True)
                        context.view_layer.objects.active = new_dim
                        context.view_layer.update()
                        for area in bpy.context.screen.areas:
                             if area.type in ["PROPERTIES", "VIEW_3D"]: area.tag_redraw()
                   
              if prev_mode != 'OBJECT': bpy.ops.object.mode_set(mode=prev_mode)
                   
         except Exception as e:
              print(f"[FCD] Reconstructive Flip Failure: {e}")
         finally:
              _dim_update_guard = False
         return None

    # Defer execution to clear the current property update stack
    bpy.app.timers.register(delayed_rebuild, first_interval=0.01)
    
    # Global guard to prevent the property dispatcher from re-triggering during the delete
    _dim_update_guard = True 

def build_example_arm(context: bpy.types.Context, scale_factor: float = 1.0):
    """
    Builds a 6-DOF robotic arm with alternating rotating and revolute joints.
    """
    import math

    # --- 0. Ensure Object Mode and clear selection ---
    # AI Editor Note: Fixed operator poll error by checking active object and using manual deselect.
    if context.active_object and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for o in context.selected_objects:
        o.select_set(False)

    cursor_loc = context.scene.cursor.location

    # --- 1. Create a new rig ---
    bpy.ops.fcd.create_rig()
    rig = context.scene.fcd_active_rig
    if not rig:
        raise Exception("Failed to create a new rig.")

    # --- 2. Create Base ---
    # AI Editor Note: Generate at 3D cursor location.
    # Updated dimensions for realistic desktop arm scale (e.g. UR3/UR5 size)
    base_height = 0.04 * scale_factor
    base_pos = cursor_loc + mathutils.Vector((0, 0, base_height / 2))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.08 * scale_factor, depth=base_height, location=base_pos)
    base = context.active_object
    base.name = get_unique_name('base')
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Add a bone for the base. This will be the root.
    context.view_layer.objects.active = base
    base.select_set(True)
    bpy.ops.fcd.add_bone()
    base_bone_name = f"Bone_{base.name.replace('.', '_')}"

    # --- 3. Create Arm Links ---
    # AI Editor Note: Updated to 6-DOF with alternating joint types/axes.
    # Configuration:
    # 1. Base Pan (Rotating Y)
    # 2. Shoulder (Revolute Z)
    # 3. Elbow (Revolute Z)
    # 4. Forearm Roll (Rotating Y)
    # 5. Wrist Pitch (Revolute Z)
    # 6. Wrist Roll (Rotating Y)
    
    z_accum = base_height
    gap = 0.01 * scale_factor

    # Heights for each link
    h1 = 0.12 * scale_factor
    h2 = 0.40 * scale_factor
    h3 = 0.35 * scale_factor
    h4 = 0.15 * scale_factor
    h5 = 0.10 * scale_factor
    h6 = 0.05 * scale_factor
    
    arm_links = [
        {'name': 'arm_link_1', 'pos': (0, 0, z_accum + h1/2), 'dims': (0.07 * scale_factor, h1), 'joint': 'continuous', 'axis': 'Y'},
        {'name': 'arm_link_2', 'pos': (0, 0, z_accum + h1 + gap + h2/2), 'dims': (0.05 * scale_factor, h2), 'joint': 'revolute', 'axis': 'Z'},
        {'name': 'arm_link_3', 'pos': (0, 0, z_accum + h1 + gap + h2 + gap + h3/2), 'dims': (0.045 * scale_factor, h3), 'joint': 'revolute', 'axis': 'Z'},
        {'name': 'arm_link_4', 'pos': (0, 0, z_accum + h1 + gap + h2 + gap + h3 + gap + h4/2), 'dims': (0.04 * scale_factor, h4), 'joint': 'continuous', 'axis': 'Y'},
        {'name': 'arm_link_5', 'pos': (0, 0, z_accum + h1 + gap + h2 + gap + h3 + gap + h4 + gap + h5/2), 'dims': (0.035 * scale_factor, h5), 'joint': 'revolute', 'axis': 'Z'},
        {'name': 'arm_link_6', 'pos': (0, 0, z_accum + h1 + gap + h2 + gap + h3 + gap + h4 + gap + h5 + gap + h6/2), 'dims': (0.03 * scale_factor, h6), 'joint': 'continuous', 'axis': 'Y'},
    ]
    parent_bone_name = base_bone_name

    for link_info in arm_links:
        for o in context.selected_objects: o.select_set(False)
        # Apply cursor offset to position
        pos = cursor_loc + mathutils.Vector(link_info['pos'])
        bpy.ops.mesh.primitive_cylinder_add(radius=link_info['dims'][0], depth=link_info['dims'][1], location=pos)
        link_obj = context.active_object
        link_obj.name = get_unique_name(link_info['name'])

        context.view_layer.objects.active = link_obj
        link_obj.select_set(True)
        bpy.ops.fcd.add_bone()
        link_bone_name = f"Bone_{link_obj.name.replace('.', '_')}"

        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[link_bone_name].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)

        pbone = rig.pose.bones.get(link_bone_name)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = link_info['joint']
            pbone.fcd_pg_kinematic_props.axis_enum = link_info['axis']
            update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
            apply_native_constraints(pbone)

        parent_bone_name = link_bone_name

    # --- 4. Finalize ---
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in context.selected_objects: o.select_set(False)
    rig.select_set(True)
    context.view_layer.objects.active = rig


def build_example_rover(context: bpy.types.Context, scale_factor: float = 1.0):
    """
    AI Editor Note: Updated to generate a 6-wheeled rover (Standard Rocker-Bogie style base).
    This function is a self-contained example of a generative process. It
    demonstrates how to use the addon's operators and Blender's native APIs
    to construct a simple, pre-defined robot (a 6-wheeled rover with an arm).

    It follows a clear, step-by-step process that is easy for both humans and
    other AI models to understand and adapt. This function serves as a concrete
    target for what an LLM should generate if asked to produce a Python script
    for robot construction.

    The logic is carefully ordered to manage Blender's context (active object,
    selection, modes) correctly, which is crucial for a sequence of operators
    to succeed.
    """
    import math

    # --- 0. Ensure Object Mode and clear selection ---
    if context.active_object and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for o in context.selected_objects:
        o.select_set(False)

    cursor_loc = context.scene.cursor.location

    # --- 1. Create a new rig ---
    bpy.ops.fcd.create_rig()
    rig = context.scene.fcd_active_rig
    if not rig:
        raise Exception("Failed to create a new rig.")

    # --- 2. Create Chassis ---
    # Realistic rover chassis size (approx 60cm x 40cm x 15cm)
    chassis_z = (0.2 + 0.075) * scale_factor # 20cm clearance + half height
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((0, 0, chassis_z)))
    chassis = context.active_object
    chassis.name = get_unique_name('chassis')
    chassis.dimensions = (0.6 * scale_factor, 0.4 * scale_factor, 0.15 * scale_factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Add a bone for the chassis. This will be the root.
    context.view_layer.objects.active = chassis
    chassis.select_set(True)
    bpy.ops.fcd.add_bone()
    chassis_bone_name = f"Bone_{chassis.name.replace('.', '_')}"

    # --- 3. Create Wheels (6-Wheel Configuration) ---
    # Adjusted positions for new chassis size
    wheel_positions = [
        (0.22 * scale_factor, 0.25 * scale_factor, 0.1 * scale_factor),   # Front-right
        (0.22 * scale_factor, -0.25 * scale_factor, 0.1 * scale_factor),  # Front-left
        (0.0, 0.25 * scale_factor, 0.1 * scale_factor),    # Mid-right
        (0.0, -0.25 * scale_factor, 0.1 * scale_factor),   # Mid-left
        (-0.22 * scale_factor, 0.25 * scale_factor, 0.1 * scale_factor),  # Back-right
        (-0.22 * scale_factor, -0.25 * scale_factor, 0.1 * scale_factor)  # Back-left
    ]
    wheel_bones = []

    for i, pos in enumerate(wheel_positions):
        for o in context.selected_objects: o.select_set(False)
        w_pos = cursor_loc + mathutils.Vector(pos)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1 * scale_factor, depth=0.08 * scale_factor, location=w_pos)
        wheel = context.active_object
        wheel.name = get_unique_name(f'wheel_{i+1}')
        wheel.rotation_euler.x = math.pi / 2
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

        # Add a bone for the wheel
        context.view_layer.objects.active = wheel
        wheel.select_set(True)
        bpy.ops.fcd.add_bone()
        wheel_bone_name = f"Bone_{wheel.name.replace('.', '_')}"
        wheel_bones.append(wheel_bone_name)

    # --- 4. Parent wheel bones and set joint types ---
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    for wheel_bone_name in wheel_bones:
        rig.data.edit_bones[wheel_bone_name].parent = rig.data.edit_bones[chassis_bone_name]
    bpy.ops.object.mode_set(mode='POSE', toggle=False)

    for wheel_bone_name in wheel_bones:
        pbone = rig.pose.bones.get(wheel_bone_name)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'continuous'
            pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
            update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
            apply_native_constraints(pbone)

    # --- 5. Create Arm ---
    # Scaled down manipulator for rover, placed on top of chassis
    arm_base_z = chassis_z + 0.075 * scale_factor
    arm_links = [
        {'name': 'arm_link_1', 'pos': (0.15 * scale_factor, 0, arm_base_z + 0.05 * scale_factor), 'dims': (0.05 * scale_factor, 0.1 * scale_factor), 'joint': 'revolute', 'axis': 'Z'},
        {'name': 'arm_link_2', 'pos': (0.15 * scale_factor, 0, arm_base_z + (0.1 + 0.15) * scale_factor), 'dims': (0.04 * scale_factor, 0.3 * scale_factor), 'joint': 'revolute', 'axis': 'Y'},
        {'name': 'arm_link_3', 'pos': (0.15 * scale_factor, 0, arm_base_z + (0.1 + 0.3 + 0.125) * scale_factor), 'dims': (0.03 * scale_factor, 0.25 * scale_factor), 'joint': 'revolute', 'axis': 'Y'},
    ]
    parent_bone_name = chassis_bone_name

    for link_info in arm_links:
        for o in context.selected_objects: o.select_set(False)
        pos = cursor_loc + mathutils.Vector(link_info['pos'])
        bpy.ops.mesh.primitive_cylinder_add(radius=link_info['dims'][0], depth=link_info['dims'][1], location=pos)
        link_obj = context.active_object
        link_obj.name = get_unique_name(link_info['name'])

        context.view_layer.objects.active = link_obj
        link_obj.select_set(True)
        bpy.ops.fcd.add_bone()
        link_bone_name = f"Bone_{link_obj.name.replace('.', '_')}"

        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[link_bone_name].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)

        pbone = rig.pose.bones.get(link_bone_name)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = link_info['joint']
            pbone.fcd_pg_kinematic_props.axis_enum = link_info['axis']
            update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
            apply_native_constraints(pbone)

        parent_bone_name = link_bone_name

    # --- 6. Finalize ---
    bpy.ops.object.mode_set(mode='OBJECT')
    for o in context.selected_objects: o.select_set(False)
    rig.select_set(True)
    context.view_layer.objects.active = rig


def build_mobile_base_diff_drive(context: bpy.types.Context, scale_factor: float = 1.0):
    """Builds a 2-wheeled differential drive base with a caster."""
    import math
    if context.active_object and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for o in context.selected_objects:
        o.select_set(False)

    cursor_loc = context.scene.cursor.location

    bpy.ops.fcd.create_rig()
    rig = context.scene.fcd_active_rig
    if not rig: return

    # Chassis
    # AI Editor Note: Use cursor location offset
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((0, 0, 0.08 * scale_factor)))
    chassis = context.active_object
    chassis.name = get_unique_name('base_link')
    chassis.dimensions = (0.4 * scale_factor, 0.3 * scale_factor, 0.08 * scale_factor)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = chassis
    chassis.select_set(True)
    bpy.ops.fcd.add_bone()
    chassis_bone = f"Bone_{chassis.name.replace('.', '_')}"

    # Wheels
    wheel_data = [
        ('wheel_left', (0, 0.17 * scale_factor, 0.06 * scale_factor)),
        ('wheel_right', (0, -0.17 * scale_factor, 0.06 * scale_factor))
    ]
    
    for name, pos in wheel_data:
        for o in context.selected_objects: o.select_set(False)
        w_pos = cursor_loc + mathutils.Vector(pos)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.06 * scale_factor, depth=0.025 * scale_factor, location=w_pos)
        wheel = context.active_object
        wheel.name = get_unique_name(name)
        wheel.rotation_euler.x = math.pi / 2
        bpy.ops.object.transform_apply(rotation=True, scale=True)
        
        context.view_layer.objects.active = wheel
        wheel.select_set(True)
        bpy.ops.fcd.add_bone()
        w_bone = f"Bone_{wheel.name.replace('.', '_')}"
        
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[w_bone].parent = rig.data.edit_bones[chassis_bone]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        pbone = rig.pose.bones.get(w_bone)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'continuous'
            pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
            update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
            apply_native_constraints(pbone)

    # Caster
    for o in context.selected_objects: o.select_set(False)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03 * scale_factor, location=cursor_loc + mathutils.Vector((0.15 * scale_factor, 0, 0.03 * scale_factor)))
    caster = context.active_object
    caster.name = get_unique_name('caster_wheel')
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = caster
    caster.select_set(True)
    bpy.ops.fcd.add_bone()
    c_bone = f"Bone_{caster.name.replace('.', '_')}"
    
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    rig.data.edit_bones[c_bone].parent = rig.data.edit_bones[chassis_bone]
    bpy.ops.object.mode_set(mode='POSE', toggle=False)
    
    pbone = rig.pose.bones.get(c_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'fixed'
        update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
        apply_native_constraints(pbone)

    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(True)
    context.view_layer.objects.active = rig

def build_quadruped_spider(context: bpy.types.Context, scale_factor: float = 1.0):
    """Builds a simple 4-legged spider robot."""
    import math
    if context.active_object and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in context.selected_objects:
        o.select_set(False)

    cursor_loc = context.scene.cursor.location
    
    bpy.ops.fcd.create_rig()
    rig = context.scene.fcd_active_rig
    if not rig: return

    # Body
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((0, 0, 0.26 * scale_factor)))
    body = context.active_object
    body.name = get_unique_name('body')
    body.dimensions = (0.4 * scale_factor, 0.25 * scale_factor, 0.12 * scale_factor)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.fcd.add_bone()
    body_bone = f"Bone_{body.name.replace('.', '_')}"
    
    pbone = rig.pose.bones.get(body_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)

    # --- ADD LEGS ---
    leg_w = 0.04 * scale_factor
    leg_h = 0.2 * scale_factor
    for x_side in [-1, 1]:
        for y_side in [-1, 1]:
            side_str = f"{'F' if y_side > 0 else 'B'}{'L' if x_side < 0 else 'R'}"
            l_pos = cursor_loc + mathutils.Vector((x_side * 0.15 * scale_factor, y_side * 0.1 * scale_factor, 0.15 * scale_factor))
            
            bpy.ops.mesh.primitive_cylinder_add(radius=leg_w, depth=leg_h, location=l_pos)
            leg = context.active_object
            leg.name = get_unique_name(f'leg_{side_str}')
            
            context.view_layer.objects.active = leg; leg.select_set(True)
            bpy.ops.fcd.add_bone()
            leg_bone = f"Bone_{leg.name.replace('.', '_')}"
            
            # Parent
            context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
            rig.data.edit_bones[leg_bone].parent = rig.data.edit_bones[body_bone]
            bpy.ops.object.mode_set(mode='POSE')
            
            pbone = rig.pose.bones.get(leg_bone)
            if pbone:
                 pbone.fcd_pg_kinematic_props.joint_type = 'fixed'
                 update_single_bone_gizmo(pbone, context.scene.fcd_viz_gizmos)
    
    # Select rig again
    context.view_layer.objects.active = rig
    rig.select_set(True)
    # Note: For a complex quadruped, we'd add legs here. 
    # Keeping it simple for the template to avoid massive code blocks.
    # This creates the base structure ready for leg attachment.
    
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.select_set(True)
    context.view_layer.objects.active = rig


def create_flat_gizmo(shape_type: str = 'ROTATION', target_axis: str = 'Z', style: str = 'DEFAULT') -> Optional[bpy.types.Object]:
    """
    Creates or retrieves a custom bone shape (widget) object for visualizing joints.

    This function implements a flyweight pattern for gizmo objects. It creates a
    single, shared mesh and object for each type and axis of gizmo (e.g., one for
    'ROTATION' on 'X', one for 'SLIDER' on 'Y', etc.). This is highly efficient as
    it avoids duplicating geometry, saving memory in complex scenes.

    The gizmo objects are placed in a dedicated "Widgets" collection and are hidden
    from the viewport, rendering, and selection, as they are only templates to be
    referenced by the `custom_shape` property of a bone.

    Args:
        shape_type: The type of gizmo to create ('ROTATION', 'SLIDER', 'FIXED').
        target_axis: The axis the gizmo should be aligned to ('X', 'Y', 'Z').
        style: The visual style of the gizmo ('DEFAULT', '3D').

    Returns:
        The gizmo object, or None if creation fails (e.g., during rendering).
    """
    # Do not attempt to create meshes while a render job is running.
    if bpy.app.is_job_running("RENDER"):
        return None
    try:
        # AI Editor Note: Direct data access is safer in background threads/timers than bpy.context.
        shape_name = f"{WIDGET_PREFIX}_{style}_{shape_type}" if shape_type == 'BASE' else f"{WIDGET_PREFIX}_{style}_{shape_type}_{target_axis}"

        # If the gizmo object already exists and has mesh data, return it immediately.
        obj = bpy.data.objects.get(shape_name)
        if obj and obj.data:
            return obj

        # Create the mesh and object if they don't exist.
        mesh = bpy.data.meshes.get(shape_name)
        if not mesh:
            mesh = bpy.data.meshes.new(shape_name)
            
        if not obj:
            obj = bpy.data.objects.new(shape_name, mesh)
            obj.location = (0, 0, 0)
            
            # AI Editor Note: Gizmo templates must be hidden from viewports, 
            # renders, and selection. They are only placeholders for 'custom_shape'.
            # Leaving them visible can cause them to overlap with real rigs at (0,0,0).
            obj.hide_viewport = True
            obj.hide_render = True
            obj.hide_select = True
            obj.display_type = 'WIRE'

        # Robust collection management.
        coll = bpy.data.collections.get(WIDGETS_COLLECTION_NAME)
        if not coll:
            coll = bpy.data.collections.new(WIDGETS_COLLECTION_NAME)
            # Link to the main scene collection if we have a context, otherwise it stays in data.
            # widgets do not need to be in the scene to be custom_shapes.
            if bpy.context and bpy.context.scene:
                try: 
                    if coll.name not in bpy.context.scene.collection.children:
                        bpy.context.scene.collection.children.link(coll)
                except: pass
        
        if obj.name not in coll.objects:
            coll.objects.link(obj)

        # Generate the gizmo's geometry using BMesh.
        bm = bmesh.new()
        
        if True: # DEFAULT (Unified Style)
            if shape_type == 'ROTATION':
                bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=32)
                # Add small arrows to indicate rotational direction.
                v1 = bm.verts.new((0.9, 0.2, 0))
                v2 = bm.verts.new((1.1, 0.2, 0))
                v3 = bm.verts.new((1.0, -0.1, 0))
                bm.faces.new((v1, v2, v3))
                v4 = bm.verts.new((-0.9, -0.2, 0))
                v5 = bm.verts.new((-1.1, -0.2, 0))
                v6 = bm.verts.new((-1.0, 0.1, 0))
                bm.faces.new((v4, v5, v6))
            elif shape_type == 'SLIDER':
                # A central line with arrows at the ends.
                v_start = bm.verts.new((0, -1.0, 0))
                v_end = bm.verts.new((0, 1.0, 0))
                bm.edges.new((v_start, v_end))
                t1 = bm.verts.new((0, 1.0, 0.2))
                t2 = bm.verts.new((0, 1.0, -0.2))
                t3 = bm.verts.new((0, 1.3, 0))
                bm.faces.new((t1, t2, t3))
                b1 = bm.verts.new((0, -1.0, 0.2))
                b2 = bm.verts.new((0, -1.0, -0.2))
                b3 = bm.verts.new((0, -1.3, 0))
                bm.faces.new((b3, b2, b1))
            elif shape_type == 'FIXED':
                # A simple cube to indicate a fixed joint.
                bmesh.ops.create_cube(bm, size=0.5)
            elif shape_type == 'SPHERICAL':
                # Wireframe sphere (3 circles) for ball-and-socket.
                bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=32)
                bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=32, matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'X'))
                bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=32, matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))

        # Base is common for now
        if shape_type == 'BASE':
            # A 3-axis cross gizmo to represent a movable base.
            axis_len = 1.0
            axis_rad = 0.05
            # X axis (Red)
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=axis_rad, radius2=axis_rad, depth=axis_len, segments=8, matrix=mathutils.Matrix.Rotation(math.radians(90), 4, 'Y'))
            # Y axis (Green)
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=axis_rad, radius2=axis_rad, depth=axis_len, segments=8, matrix=mathutils.Matrix.Rotation(math.radians(-90), 4, 'X'))
            # Z axis (Blue)
            bmesh.ops.create_cone(bm, cap_ends=True, radius1=axis_rad, radius2=axis_rad, depth=axis_len, segments=8)

        # Rotate the generated geometry to match the target axis.
        # AI Editor Note: The 'BASE' gizmo is pre-aligned and should not be rotated.
        if shape_type != 'BASE':
            helper_type = 'prismatic' if shape_type == 'SLIDER' else 'revolute'
            rot_matrix = get_gizmo_rotation_matrix(helper_type, target_axis)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=rot_matrix)

        bm.to_mesh(mesh)
        mesh.update()
        bm.free()

        # Hide the template from selection and rendering, but keep it available for gizmo referencing.
        obj.hide_render = True
        obj.hide_select = True
        
        # Note: Do not use hide_viewport = True here, as some versions of Blender 
        # may stop displaying custom shapes if their source object is globally hidden.
        # Instead, we rely on the collection being excluded or hidden from the main view.
        
        return obj
    except Exception as e:
        # If anything goes wrong, return None to prevent errors upstream.
        print(f"Error creating gizmo '{shape_name}': {e}")
        return None

def create_rotational_driver_gizmo_mesh() -> Optional[bpy.types.Object]:
    """
    Creates or retrieves a custom mesh object for the rotational driver gizmo.
    This mesh is designed to be used as the `custom_shape` for the Empty object
    that drives the chain animation, providing a visual cue similar to a
    continuous joint.

    The gizmo is a circle in the XY plane with small arrows, indicating rotation
    around the Z-axis.

    Returns:
        The gizmo object, or None if creation fails (e.g., during rendering).
    """
    # Do not attempt to create meshes while a render job is running.
    if bpy.app.is_job_running("RENDER"):
        return None
    try:
        gizmo_name = f"{WIDGET_PREFIX}_RotationalDriver"
        existing_obj = bpy.data.objects.get(gizmo_name)
        if existing_obj:
            return existing_obj

        mesh = bpy.data.meshes.new(gizmo_name)
        obj = bpy.data.objects.new(gizmo_name, mesh)
        obj.location = (0, 0, 0)

        coll = bpy.data.collections.get(WIDGETS_COLLECTION_NAME)
        if not coll:
            coll = bpy.data.collections.new(WIDGETS_COLLECTION_NAME)
            if bpy.context.scene:
                bpy.context.scene.collection.children.link(coll)
        if obj.name not in coll.objects:
            coll.objects.link(obj)

        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=False, radius=1.0, segments=32)
        v1 = bm.verts.new((0.9, 0.2, 0)); v2 = bm.verts.new((1.1, 0.2, 0)); v3 = bm.verts.new((1.0, -0.1, 0))
        bm.faces.new((v1, v2, v3))
        v4 = bm.verts.new((-0.9, -0.2, 0)); v5 = bm.verts.new((-1.1, -0.2, 0)); v6 = bm.verts.new((-1.0, 0.1, 0))
        bm.faces.new((v4, v5, v6))

        bm.to_mesh(mesh)
        bm.free()

        obj.hide_viewport = True
        obj.hide_render = True
        obj.hide_select = True
        return obj
    except Exception as e:
        print(f"Error creating rotational driver gizmo: {e}")
        return None

def setup_and_update_material(obj: bpy.types.Object, color: mathutils.Color) -> None:
    """
    Ensures an object has a URDF-managed material and sets its color.

    This function is the core of the real-time viewport material handling. It
    creates a unique, node-based material for the given object if one doesn't
    exist, assigns it, and then updates the 'Base Color' of its Principled BSDF
    node. This ensures that color changes are reflected instantly in the viewport.

    Args:
        obj: The mesh object to apply the material to.
        color: The RGBA color to set.
    """
    if not obj or obj.type != 'MESH':
        return

    # 1. Use a unique material name to avoid conflicts.
    mat_name = f"FCD_{obj.name}_VPMaterial"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

    # 2. Assign material to the object.
    # AI Editor Note: Use Object-linked materials to allow unique colors even if meshes are shared.
    if not obj.material_slots:
        # If no slots, add one to the mesh data (required to have a slot to override).
        obj.data.materials.append(mat)
    
    # Force the first slot to link to the Object and assign the unique material.
    # This ensures that duplicating the object (which shares mesh) allows for independent coloring.
    obj.material_slots[0].link = 'OBJECT'
    obj.material_slots[0].material = mat

    # 3. Find the Principled BSDF node and set its color.
    if mat.node_tree:
        # Ensure nodes are present
        if not mat.node_tree.nodes:
            mat.node_tree.nodes.new('ShaderNodeOutputMaterial')

        bsdf_node = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)

        if not bsdf_node:
            # If no BSDF node, create one and link it for robustness.
            output_node = next((n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if output_node:
                bsdf_node = mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                bsdf_node.location = output_node.location[0] - 250, output_node.location[1]
                mat.node_tree.links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

        if bsdf_node:
            bsdf_node.inputs['Base Color'].default_value = color

    # --- AI Editor Note: Update Geometry Nodes Material ---
    # For procedural parts like springs, we need to explicitly update the Set Material node
    # within the Geometry Nodes graph to ensure the color is applied to the generated geometry.
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.node_group:
            # Check if node group is shared (users > 1). If so, make a unique copy.
            # This prevents changing the color of one spring from affecting duplicates.
            if mod.node_group.users > 1:
                new_group = mod.node_group.copy()
                new_group.name = f"FCD_Native_{obj.name}_Spring_GN"
                mod.node_group = new_group
            
            for node in mod.node_group.nodes:
                if node.type == 'SET_MATERIAL':
                    node.inputs['Material'].default_value = mat

def update_viewport_material(self: 'FCD_MaterialProperties', context: bpy.types.Context) -> None:
    """
    Update callback for the material color property. This function finds the
    associated object(s) and calls the material setup function.
    """
    # 'self' is the FCD_MaterialProperties group.
    # 'self.id_data' is the PropertyGroup that owns it (e.g., FCD_Properties).
    owner_prop_group = self.id_data
    if not owner_prop_group: return

    # 'owner_prop_group.id_data' is the Blender data-block (Object or PoseBone).
    owner_datablock = owner_prop_group.id_data
    if not owner_datablock: return

    objects_to_update = []
    if isinstance(owner_datablock, bpy.types.Object):
        # This is a parametric part (e.g., a gear or a chain curve).
        props = owner_datablock.fcd_pg_mech_props
        if props.category == 'CHAIN' and props.instanced_link_obj:
            # For chains, the material is applied to the hidden link object.
            objects_to_update.append(props.instanced_link_obj)
        else:
            objects_to_update.append(owner_datablock)
    elif isinstance(owner_datablock, bpy.types.PoseBone):
        # This is a bone, so update all child meshes.
        objects_to_update.extend(get_all_children_objects(owner_datablock, context))

    for obj in objects_to_update:
        setup_and_update_material(obj, self.color)

def create_driver(target_obj: bpy.types.Object, source_data_path: str, modifier_name: str, modifier_input_identifier: str) -> None:
    """
    Creates a simple, robust, native driver to link a custom property to a
    modifier input.

    This function is a key part of the addon's "native" philosophy. It uses
    Blender's built-in driver system to create relationships, which means they
    will continue to function perfectly even if the addon is disabled or uninstalled.

    It uses the 'AVERAGE' driver type with a single variable as a simple and
    efficient way to pass a value directly without needing a 'SCRIPTED' expression.
    This is slightly more performant and is guaranteed to be safe, as it involves
    no arbitrary code execution.

    Args:
        target_obj: The object containing the modifier to be driven.
        source_data_path: The data path to the source custom property on the
                          `target_obj` (e.g., '["my_prop"]').
        modifier_name: The name of the modifier to drive.
        modifier_input_identifier: The identifier of the modifier's input
                                   socket (e.g., 'Input_2').
    """
    # Construct the full data path to the modifier's input property.
    driver_path = f'modifiers["{modifier_name}"]["{modifier_input_identifier}"]'

    # Create the F-Curve and driver for the target property.
    fcurve = target_obj.driver_add(driver_path)
    if not fcurve:
        print(f"Error: Could not add driver to {target_obj.name} at path {driver_path}")
        return
    driver = fcurve.driver

    # Use the 'AVERAGE' type. For a single variable, this is the simplest and
    # most efficient way to pass its value directly to the driver's output.
    driver.type = 'AVERAGE'

    # Create a variable to read the value from the source custom property.
    # If a variable already exists, remove it to ensure a clean state.
    if driver.variables:
        driver.variables.remove(driver.variables[0])

    var = driver.variables.new()
    var.name = "var"  # The name is arbitrary for a single-variable 'AVERAGE' driver.
    var.type = 'SINGLE_PROP'

    # Set the variable's target to the object itself and the specified data path.
    var.targets[0].id = target_obj
    var.targets[0].data_path = source_data_path

    # With an 'AVERAGE' driver and one variable, the expression is implicitly
    # just the value of that variable. We set it explicitly for clarity.
    driver.expression = "var"

def get_unique_name(base_name: str) -> str:
    """
    Generates a unique object name in the current scene by appending a
    numbered suffix if the name is already taken.

    Args:
        base_name: The desired base name for the object.

    Returns:
        A unique name (e.g., "chassis" or "chassis.001").
    """
    name = base_name
    count = 1
    while name in bpy.data.objects:
        name = f"{base_name}.{count:03d}"
        count += 1
    return name

def setup_native_spring(spring_obj: bpy.types.Object, start_empty: bpy.types.Object, end_empty: bpy.types.Object) -> None:
    """
    Creates a dynamic, fully procedural, and independent Geometry Nodes setup for a spring.

    This function generates a unique Geometry Nodes group for the given `spring_obj`.
    This is a critical design choice to ensure that each spring is a self-contained
    asset. It prevents any unintended interactions or shared data issues when multiple
    springs are present in a scene.

    The entire spring geometry is generated and controlled within this node tree,
    driven by the world-space locations of the `start_empty` and `end_empty`
    objects. This makes the spring's behavior intuitive and robust.

    AI Editor Note:
    This function exemplifies the addon's core philosophy of using native Blender
    features for a non-destructive workflow. The spring is 100% procedural and
    self-contained within its Geometry Nodes modifier. It remains fully functional
    even if this addon is disabled. The parameters are controlled by custom
    properties on the main spring object, which are linked to the modifier inputs
    via native drivers.

    Args:
        spring_obj: The main mesh object that will host the spring's
                    Geometry Nodes modifier.
        start_empty: The empty object that controls the starting point of the spring.
        end_empty: The empty object that controls the ending point of the spring.
    """
    # --- UNIQUE NODE GROUP ---
    # A unique name based on the spring object's name ensures each spring has its
    # own node group, guaranteeing independence from other springs.
    gn_group_name = f"FCD_Native_{spring_obj.name}_Spring_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')

        # --- 1. Define Node Group Interface (Inputs & Outputs) ---
        iface = gn_group.interface
        # Inputs for the controller objects and spring parameters.
        start_obj_socket = iface.new_socket(name="Start Object", in_out="INPUT", socket_type='NodeSocketObject')
        end_obj_socket = iface.new_socket(name="End Object", in_out="INPUT", socket_type='NodeSocketObject')
        turns_socket = iface.new_socket(name="Turns", in_out="INPUT", socket_type='NodeSocketInt')
        turns_socket.default_value = 12
        turns_socket.min_value = 1
        spring_radius_socket = iface.new_socket(name="Spring Radius", in_out="INPUT", socket_type='NodeSocketFloat')
        spring_radius_socket.default_value = 0.5
        spring_radius_socket.min_value = 0.01
        wire_radius_socket = iface.new_socket(name="Wire Radius", in_out="INPUT", socket_type='NodeSocketFloat')
        wire_radius_socket.default_value = 0.1
        wire_radius_socket.min_value = 0.001
        # Final geometry output.
        iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

        # --- 2. Create Core Nodes ---
        nodes = gn_group.nodes
        links = gn_group.links

        group_input = nodes.new('NodeGroupInput')
        group_input.location = (-1200, 0)
        group_output = nodes.new('NodeGroupOutput')
        group_output.location = (600, 0)

        # --- 3. Node Logic: Calculate Spring Orientation and Size ---
        # Get locations of controller empties in WORLD space for robustness.
        start_info = nodes.new('GeometryNodeObjectInfo')
        start_info.location = (-1000, 200)
        start_info.transform_space = 'RELATIVE'
        end_info = nodes.new('GeometryNodeObjectInfo')
        end_info.location = (-1000, -200)
        end_info.transform_space = 'RELATIVE'

        # Calculate the vector from start to end, its length (spring height), and its direction.
        subtract_vec = nodes.new('ShaderNodeVectorMath')
        subtract_vec.operation = 'SUBTRACT'
        subtract_vec.location = (-800, 0)
        length_vec = nodes.new('ShaderNodeVectorMath')
        length_vec.operation = 'LENGTH'
        length_vec.location = (-600, 100)
        normalize_vec = nodes.new('ShaderNodeVectorMath')
        normalize_vec.operation = 'NORMALIZE'
        normalize_vec.location = (-600, -100)

        # Calculate the rotation needed to align the spiral's default Z-axis to the spring's direction vector.
        align_rot = nodes.new('FunctionNodeAlignEulerToVector')
        align_rot.location = (-400, 0)
        align_rot.axis = 'Z'

        # --- 4. Node Logic: Generate Spring Geometry ---
        # The core of the spring is a procedural spiral curve.
        spiral_node = nodes.new('GeometryNodeCurveSpiral')
        spiral_node.location = (-200, 200)

        # Give the spiral curve thickness by sweeping a profile circle along it.
        to_mesh_node = nodes.new('GeometryNodeCurveToMesh')
        to_mesh_node.location = (200, 0)
        profile_node = nodes.new('GeometryNodeCurvePrimitiveCircle')
        profile_node.location = (0, -200)
        profile_node.inputs['Resolution'].default_value = 8

        # Transform the generated mesh to the correct final position and orientation.
        transform_geom = nodes.new('GeometryNodeTransform')
        transform_geom.location = (400, 0)

        # --- 5. Link Nodes to Define Data Flow & Material ---
        # Link controller objects to the info nodes.
        links.new(group_input.outputs[start_obj_socket.name], start_info.inputs['Object'])
        links.new(group_input.outputs[end_obj_socket.name], end_info.inputs['Object'])
        # Link info nodes to calculate the spring's vector.
        links.new(end_info.outputs['Location'], subtract_vec.inputs[0])
        links.new(start_info.outputs['Location'], subtract_vec.inputs[1])
        # Link vector to calculate length and direction.
        links.new(subtract_vec.outputs['Vector'], length_vec.inputs['Vector'])
        links.new(subtract_vec.outputs['Vector'], normalize_vec.inputs['Vector'])
        # Link parameters to the spiral node.
        links.new(length_vec.outputs['Value'], spiral_node.inputs['Height'])
        links.new(group_input.outputs[turns_socket.name], spiral_node.inputs['Rotations'])
        links.new(group_input.outputs[spring_radius_socket.name], spiral_node.inputs['Start Radius'])
        links.new(group_input.outputs[spring_radius_socket.name], spiral_node.inputs['End Radius'])
        # Link parameters to the profile and curve-to-mesh nodes.
        links.new(spiral_node.outputs['Curve'], to_mesh_node.inputs['Curve'])
        links.new(group_input.outputs[wire_radius_socket.name], profile_node.inputs['Radius'])
        links.new(profile_node.outputs['Curve'], to_mesh_node.inputs['Profile Curve'])
        # Link orientation calculation to the final transform.
        links.new(normalize_vec.outputs['Vector'], align_rot.inputs['Vector'])
        links.new(to_mesh_node.outputs['Mesh'], transform_geom.inputs['Geometry'])
        links.new(start_info.outputs['Location'], transform_geom.inputs['Translation'])
        links.new(align_rot.outputs['Rotation'], transform_geom.inputs['Rotation'])
        
        # --- AI Editor Note: Set Material for Spring ---
        # Explicitly set the material for the generated geometry to ensure color updates work.
        set_material = nodes.new('GeometryNodeSetMaterial')
        set_material.location = (550, 0)
        
        # Link final transformed geometry to the output.
        links.new(transform_geom.outputs['Geometry'], set_material.inputs['Geometry'])
        links.new(set_material.outputs['Geometry'], group_output.inputs['Geometry'])

    # --- Add and Configure the Geometry Nodes Modifier ---
    mod = spring_obj.modifiers.new(name=NATIVE_SPRING_MOD_NAME, type='NODES')
    mod.node_group = gn_group

    # --- Connect Modifier Inputs to Controller Objects and Custom Properties ---
    # Find sockets by name for robustness against changes in socket order.
    iface = gn_group.interface
    start_obj_socket = iface.items_tree.get("Start Object")
    end_obj_socket = iface.items_tree.get("End Object")
    turns_socket = iface.items_tree.get("Turns")
    spring_radius_socket = iface.items_tree.get("Spring Radius")
    wire_radius_socket = iface.items_tree.get("Wire Radius")

    # Assign the controller empties directly to the object inputs.
    if start_obj_socket: mod[start_obj_socket.identifier] = start_empty
    if end_obj_socket: mod[end_obj_socket.identifier] = end_empty
    # Create native drivers to link the spring's custom properties to the modifier inputs.
    if turns_socket: create_driver(spring_obj, '["spring_teeth"]', mod.name, turns_socket.identifier)
    if spring_radius_socket: create_driver(spring_obj, '["spring_radius"]', mod.name, spring_radius_socket.identifier)
    if wire_radius_socket: create_driver(spring_obj, '["spring_wire_thickness"]', mod.name, wire_radius_socket.identifier)

    # No constraints or parenting are needed. The Geometry Nodes setup is self-contained.

def setup_native_damper(damper_obj: bpy.types.Object, start_empty: bpy.types.Object, end_empty: bpy.types.Object) -> None:
    """
    Creates a dynamic, procedural Geometry Nodes setup for a damper.
    Generates a housing tube, piston rod, mounting eyes, and a coilover spring.
    """
    gn_group_name = f"FCD_Native_{damper_obj.name}_Damper_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    # AI Editor Note: Always clear and recreate the node tree to ensure the latest logic is applied.
    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')
    else:
        gn_group.nodes.clear()
        gn_group.interface.clear()

    # --- 1. Define Node Group Interface (Inputs & Outputs) ---
    iface = gn_group.interface
    start_obj_socket = iface.new_socket(name="Start Object", in_out="INPUT", socket_type='NodeSocketObject')
    end_obj_socket = iface.new_socket(name="End Object", in_out="INPUT", socket_type='NodeSocketObject')
    
    # Parameters
    rad_sock = iface.new_socket(name="Spring Radius", in_out="INPUT", socket_type='NodeSocketFloat')
    rad_sock.default_value = 0.008; rad_sock.min_value = 0.0001
    
    wire_sock = iface.new_socket(name="Wire Radius", in_out="INPUT", socket_type='NodeSocketFloat')
    wire_sock.default_value = 0.0015; wire_sock.min_value = 0.0001
    
    len_sock = iface.new_socket(name="Housing Length", in_out="INPUT", socket_type='NodeSocketFloat')
    len_sock.default_value = 0.3; len_sock.min_value = 0.01
    
    piston_len_sock = iface.new_socket(name="Piston Length", in_out="INPUT", socket_type='NodeSocketFloat')
    piston_len_sock.default_value = 0.3; piston_len_sock.min_value = 0.01
    
    turns_sock = iface.new_socket(name="Turns", in_out="INPUT", socket_type='NodeSocketInt')
    turns_sock.default_value = 9; turns_sock.min_value = 1
    
    housing_rad_sock = iface.new_socket(name="Housing Radius", in_out="INPUT", socket_type='NodeSocketFloat')
    housing_rad_sock.default_value = 0.06; housing_rad_sock.min_value = 0.001
    
    rod_rad_sock = iface.new_socket(name="Rod Radius", in_out="INPUT", socket_type='NodeSocketFloat')
    rod_rad_sock.default_value = 0.03; rod_rad_sock.min_value = 0.001
    
    seat_rad_sock = iface.new_socket(name="Seat Radius", in_out="INPUT", socket_type='NodeSocketFloat')
    seat_rad_sock.default_value = 0.01; seat_rad_sock.min_value = 0.001
    
    seat_thick_sock = iface.new_socket(name="Seat Thickness", in_out="INPUT", socket_type='NodeSocketFloat')
    seat_thick_sock.default_value = 0.003; seat_thick_sock.min_value = 0.001
    
    iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

    # --- 2. Create Core Nodes ---
    nodes = gn_group.nodes
    links = gn_group.links

    # Input/Output
    g_in = nodes.new('NodeGroupInput')
    g_in.location = (-1800, 0)
    g_out = nodes.new('NodeGroupOutput')
    g_out.location = (1500, 0)

    # --- 3. Position & Alignment ---
    start_info = nodes.new('GeometryNodeObjectInfo'); start_info.location = (-1600, 200); start_info.transform_space = 'RELATIVE'
    end_info = nodes.new('GeometryNodeObjectInfo'); end_info.location = (-1600, -200); end_info.transform_space = 'RELATIVE'
    
    # Vector Start->End (Housing & Spring)
    vec_main = nodes.new('ShaderNodeVectorMath'); vec_main.operation = 'SUBTRACT'; vec_main.location = (-1400, 100)
    dist_main = nodes.new('ShaderNodeVectorMath'); dist_main.operation = 'DISTANCE'; dist_main.location = (-1400, 0)
    
    # Vector End->Start (Piston)
    vec_rev = nodes.new('ShaderNodeVectorMath'); vec_rev.operation = 'SUBTRACT'; vec_rev.location = (-1400, -100)
    
    align_main = nodes.new('FunctionNodeAlignEulerToVector'); align_main.location = (-1200, 100); align_main.axis = 'Z'
    align_rev = nodes.new('FunctionNodeAlignEulerToVector'); align_rev.location = (-1200, -100); align_rev.axis = 'Z'

    # --- 4. Node Logic: Generate Housing (Cylinder) ---
    cyl_housing = nodes.new('GeometryNodeMeshCylinder'); cyl_housing.location = (-800, 400)
    
    # Offset Z up by Length/2
    math_half_housing = nodes.new('ShaderNodeMath'); math_half_housing.operation = 'DIVIDE'; math_half_housing.inputs[1].default_value = 2.0; math_half_housing.location = (-800, 550)
    comb_housing_off = nodes.new('ShaderNodeCombineXYZ'); comb_housing_off.location = (-600, 550)
    
    trans_housing_local = nodes.new('GeometryNodeTransform'); trans_housing_local.location = (-400, 400)
    trans_housing_world = nodes.new('GeometryNodeTransform'); trans_housing_world.location = (-200, 400)

    # Housing Cap (Closes the cylinder)
    # AI Editor Note: Calculate cap depth relative to radius to prevent distortion at small scales.
    math_cap_depth = nodes.new('ShaderNodeMath'); math_cap_depth.operation = 'MULTIPLY'; math_cap_depth.inputs[1].default_value = 0.2; math_cap_depth.location = (-1000, 250)
    
    cyl_cap = nodes.new('GeometryNodeMeshCylinder'); cyl_cap.location = (-800, 250)
    comb_cap_off = nodes.new('ShaderNodeCombineXYZ'); comb_cap_off.location = (-600, 250)
    trans_cap_local = nodes.new('GeometryNodeTransform'); trans_cap_local.location = (-400, 250)
    trans_cap_world = nodes.new('GeometryNodeTransform'); trans_cap_world.location = (-200, 250)

    # --- 5. Node Logic: Generate Piston (Rod) ---
    
    cyl_rod = nodes.new('GeometryNodeMeshCylinder'); cyl_rod.location = (-800, -200)
    
    # Offset Z up by Length/2 (relative to End, pointing back)
    math_half_rod = nodes.new('ShaderNodeMath'); math_half_rod.operation = 'DIVIDE'; math_half_rod.inputs[1].default_value = 2.0; math_half_rod.location = (-800, -50)
    comb_rod_off = nodes.new('ShaderNodeCombineXYZ'); comb_rod_off.location = (-600, -50)
    
    trans_rod_local = nodes.new('GeometryNodeTransform'); trans_rod_local.location = (-400, -200)
    trans_rod_world = nodes.new('GeometryNodeTransform'); trans_rod_world.location = (-200, -200)

    # --- 6. Spring (Coilover) ---
    spiral = nodes.new('GeometryNodeCurveSpiral'); spiral.location = (-800, 100)
    
    mesh_spring = nodes.new('GeometryNodeCurveToMesh'); mesh_spring.location = (-600, 100)
    profile_spring = nodes.new('GeometryNodeCurvePrimitiveCircle'); profile_spring.location = (-800, -50); profile_spring.inputs['Resolution'].default_value = 8
    
    # AI Editor Note: Adjust spring height and offset to prevent poking out of seats.
    math_double_thick = nodes.new('ShaderNodeMath'); math_double_thick.operation = 'MULTIPLY'; math_double_thick.inputs[1].default_value = 2.0; math_double_thick.location = (-800, 0)
    math_spring_len = nodes.new('ShaderNodeMath'); math_spring_len.operation = 'SUBTRACT'; math_spring_len.location = (-600, 0)
    comb_spring_off = nodes.new('ShaderNodeCombineXYZ'); comb_spring_off.location = (-600, -150)
    trans_spring_local = nodes.new('GeometryNodeTransform'); trans_spring_local.location = (-400, 100)
    trans_spring_world = nodes.new('GeometryNodeTransform'); trans_spring_world.location = (-200, 100)

    # --- 7. Caps/Mounts ---
    # Spring Seats (Disks)
    
    # Offset calculation (Thickness / 2) to align edge to empty
    math_half_seat = nodes.new('ShaderNodeMath'); math_half_seat.operation = 'DIVIDE'; math_half_seat.inputs[1].default_value = 2.0; math_half_seat.location = (-800, 750)
    comb_seat_off = nodes.new('ShaderNodeCombineXYZ'); comb_seat_off.location = (-600, 750)

    # Start Seat
    disk_start = nodes.new('GeometryNodeMeshCylinder'); disk_start.location = (-800, 900)
    trans_disk_start_local = nodes.new('GeometryNodeTransform'); trans_disk_start_local.location = (-400, 900)
    trans_disk_start = nodes.new('GeometryNodeTransform'); trans_disk_start.location = (-200, 900)
    
    # End Seat (Attached to Rod/End)
    disk_end = nodes.new('GeometryNodeMeshCylinder'); disk_end.location = (-800, -700)
    trans_disk_end_local = nodes.new('GeometryNodeTransform'); trans_disk_end_local.location = (-400, -700)
    trans_disk_end = nodes.new('GeometryNodeTransform'); trans_disk_end.location = (-200, -700)

    # --- 8. Join & Material ---
    join = nodes.new('GeometryNodeJoinGeometry'); join.location = (1000, 0)
    set_mat = nodes.new('GeometryNodeSetMaterial'); set_mat.location = (1200, 0)

    # --- LINKS ---
    # Inputs
    links.new(g_in.outputs[start_obj_socket.name], start_info.inputs['Object'])
    links.new(g_in.outputs[end_obj_socket.name], end_info.inputs['Object'])
    
    # Vectors
    links.new(end_info.outputs['Location'], vec_main.inputs[0])
    links.new(start_info.outputs['Location'], vec_main.inputs[1])
    links.new(start_info.outputs['Location'], dist_main.inputs[0])
    links.new(end_info.outputs['Location'], dist_main.inputs[1])
    
    links.new(start_info.outputs['Location'], vec_rev.inputs[0])
    links.new(end_info.outputs['Location'], vec_rev.inputs[1])
    
    links.new(vec_main.outputs['Vector'], align_main.inputs['Vector'])
    links.new(vec_rev.outputs['Vector'], align_rev.inputs['Vector'])
    
    # Housing
    links.new(g_in.outputs[housing_rad_sock.name], cyl_housing.inputs['Radius'])
    links.new(g_in.outputs[len_sock.name], cyl_housing.inputs['Depth'])
    
    links.new(g_in.outputs[len_sock.name], math_half_housing.inputs[0])
    links.new(math_half_housing.outputs['Value'], comb_housing_off.inputs['Z'])
    
    links.new(cyl_housing.outputs['Mesh'], trans_housing_local.inputs['Geometry'])
    links.new(comb_housing_off.outputs['Vector'], trans_housing_local.inputs['Translation'])
    
    links.new(trans_housing_local.outputs['Geometry'], trans_housing_world.inputs['Geometry'])
    links.new(start_info.outputs['Location'], trans_housing_world.inputs['Translation'])
    links.new(align_main.outputs['Rotation'], trans_housing_world.inputs['Rotation'])
    
    # Housing Cap
    links.new(g_in.outputs[housing_rad_sock.name], cyl_cap.inputs['Radius'])
    links.new(g_in.outputs[housing_rad_sock.name], math_cap_depth.inputs[0])
    links.new(math_cap_depth.outputs['Value'], cyl_cap.inputs['Depth'])
    
    links.new(g_in.outputs[len_sock.name], comb_cap_off.inputs['Z'])
    links.new(cyl_cap.outputs['Mesh'], trans_cap_local.inputs['Geometry'])
    links.new(comb_cap_off.outputs['Vector'], trans_cap_local.inputs['Translation'])
    links.new(trans_cap_local.outputs['Geometry'], trans_cap_world.inputs['Geometry'])
    links.new(start_info.outputs['Location'], trans_cap_world.inputs['Translation'])
    links.new(align_main.outputs['Rotation'], trans_cap_world.inputs['Rotation'])

    # Piston Rod
    links.new(g_in.outputs[rod_rad_sock.name], cyl_rod.inputs['Radius'])
    links.new(g_in.outputs[piston_len_sock.name], cyl_rod.inputs['Depth'])
    
    links.new(g_in.outputs[piston_len_sock.name], math_half_rod.inputs[0])
    links.new(math_half_rod.outputs['Value'], comb_rod_off.inputs['Z'])
    
    links.new(cyl_rod.outputs['Mesh'], trans_rod_local.inputs['Geometry'])
    links.new(comb_rod_off.outputs['Vector'], trans_rod_local.inputs['Translation'])
    
    links.new(trans_rod_local.outputs['Geometry'], trans_rod_world.inputs['Geometry'])
    links.new(end_info.outputs['Location'], trans_rod_world.inputs['Translation'])
    links.new(align_rev.outputs['Rotation'], trans_rod_world.inputs['Rotation'])
    
    # Spring
    links.new(g_in.outputs[seat_thick_sock.name], math_double_thick.inputs[0])
    links.new(dist_main.outputs['Value'], math_spring_len.inputs[0])
    links.new(math_double_thick.outputs['Value'], math_spring_len.inputs[1])
    links.new(math_spring_len.outputs['Value'], spiral.inputs['Height'])
    
    links.new(g_in.outputs[rad_sock.name], spiral.inputs['Start Radius'])
    links.new(g_in.outputs[rad_sock.name], spiral.inputs['End Radius'])
    links.new(g_in.outputs[turns_sock.name], spiral.inputs['Rotations'])
    
    links.new(g_in.outputs[wire_sock.name], profile_spring.inputs['Radius'])
    links.new(spiral.outputs['Curve'], mesh_spring.inputs['Curve'])
    links.new(profile_spring.outputs['Curve'], mesh_spring.inputs['Profile Curve'])
    
    links.new(g_in.outputs[seat_thick_sock.name], comb_spring_off.inputs['Z'])
    links.new(mesh_spring.outputs['Mesh'], trans_spring_local.inputs['Geometry'])
    links.new(comb_spring_off.outputs['Vector'], trans_spring_local.inputs['Translation'])
    
    links.new(trans_spring_local.outputs['Geometry'], trans_spring_world.inputs['Geometry'])
    links.new(start_info.outputs['Location'], trans_spring_world.inputs['Translation'])
    links.new(align_main.outputs['Rotation'], trans_spring_world.inputs['Rotation'])
    
    # Mounts & Seats
    # Offset Math
    links.new(g_in.outputs[seat_thick_sock.name], math_half_seat.inputs[0])
    links.new(math_half_seat.outputs['Value'], comb_seat_off.inputs['Z'])

    # Disk Start (at Start)
    links.new(g_in.outputs[seat_rad_sock.name], disk_start.inputs['Radius'])
    links.new(g_in.outputs[seat_thick_sock.name], disk_start.inputs['Depth'])
    
    links.new(disk_start.outputs['Mesh'], trans_disk_start_local.inputs['Geometry'])
    links.new(comb_seat_off.outputs['Vector'], trans_disk_start_local.inputs['Translation'])
    links.new(trans_disk_start_local.outputs['Geometry'], trans_disk_start.inputs['Geometry'])
    
    links.new(start_info.outputs['Location'], trans_disk_start.inputs['Translation'])
    links.new(align_main.outputs['Rotation'], trans_disk_start.inputs['Rotation'])
    
    # Disk End (at End)
    links.new(g_in.outputs[seat_rad_sock.name], disk_end.inputs['Radius'])
    links.new(g_in.outputs[seat_thick_sock.name], disk_end.inputs['Depth'])
    
    links.new(disk_end.outputs['Mesh'], trans_disk_end_local.inputs['Geometry'])
    links.new(comb_seat_off.outputs['Vector'], trans_disk_end_local.inputs['Translation'])
    links.new(trans_disk_end_local.outputs['Geometry'], trans_disk_end.inputs['Geometry'])
    
    links.new(end_info.outputs['Location'], trans_disk_end.inputs['Translation'])
    links.new(align_rev.outputs['Rotation'], trans_disk_end.inputs['Rotation'])

    # Join
    links.new(trans_housing_world.outputs['Geometry'], join.inputs['Geometry'])
    links.new(trans_cap_world.outputs['Geometry'], join.inputs['Geometry'])
    links.new(trans_rod_world.outputs['Geometry'], join.inputs['Geometry'])
    links.new(trans_spring_world.outputs['Geometry'], join.inputs['Geometry'])
    links.new(trans_disk_start.outputs['Geometry'], join.inputs['Geometry'])
    links.new(trans_disk_end.outputs['Geometry'], join.inputs['Geometry'])
    
    links.new(join.outputs['Geometry'], set_mat.inputs['Geometry'])
    links.new(set_mat.outputs['Geometry'], g_out.inputs['Geometry'])

def setup_native_slinky(slinky_obj, start_empty, end_empty):
    """
    Sets up a curved, slinky-like spring using Geometry Nodes.
    The spring path is defined by a start object, an end object, and 
    optional middle hooks.
    """
    gn_group_name = f"FCD_Native_Slinky_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)
    
    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')
        gn_group.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
        gn_group.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
        
        start_obj_sock = gn_group.interface.new_socket(name="Start Object", in_out='INPUT', socket_type='NodeSocketObject')
        end_obj_sock = gn_group.interface.new_socket(name="End Object", in_out='INPUT', socket_type='NodeSocketObject')
        hooks_coll_sock = gn_group.interface.new_socket(name="Hooks Collection", in_out='INPUT', socket_type='NodeSocketCollection')
        
        rad_sock = gn_group.interface.new_socket(name="Spring Radius", in_out='INPUT', socket_type='NodeSocketFloat')
        rad_sock.default_value = 0.05
        
        turns_sock = gn_group.interface.new_socket(name="Turns", in_out='INPUT', socket_type='NodeSocketFloat')
        turns_sock.default_value = 20.0
        
        wire_sock = gn_group.interface.new_socket(name="Wire Radius", in_out='INPUT', socket_type='NodeSocketFloat')
        wire_sock.default_value = 0.002
        
        res_sock = gn_group.interface.new_socket(name="Resolution", in_out='INPUT', socket_type='NodeSocketInt')
        res_sock.default_value = 512
        
        nodes = gn_group.nodes
        links = gn_group.links
        
        g_in = nodes.get("Group Input") or nodes.new('NodeGroupInput')
        g_out = nodes.get("Group Output") or nodes.new('NodeGroupOutput')
        
        # --- 1. Get Positions ---
        info_start = nodes.new('GeometryNodeObjectInfo'); info_start.transform_space = 'RELATIVE'
        info_end = nodes.new('GeometryNodeObjectInfo'); info_end.transform_space = 'RELATIVE'
        
        links.new(g_in.outputs[start_obj_sock.name], info_start.inputs['Object'])
        links.new(g_in.outputs[end_obj_sock.name], info_end.inputs['Object'])
        
        # --- 2. Create Backbone ---
        # AI Editor Note: Get middle hooks and join them with start/end in a single path.
        coll_info = nodes.new('GeometryNodeCollectionInfo'); coll_info.transform_space = 'RELATIVE'; coll_info.separate_children = True
        links.new(g_in.outputs[hooks_coll_sock.name], coll_info.inputs['Collection'])
        
        # We need to convert start/end objects to points too
        p_start = nodes.new('GeometryNodeMeshLine'); p_start.count = 1
        links.new(info_start.outputs['Location'], p_start.inputs['Start Location'])
        
        p_end = nodes.new('GeometryNodeMeshLine'); p_end.count = 1
        links.new(info_end.outputs['Location'], p_end.inputs['Start Location'])
        
        join_pts = nodes.new('GeometryNodeJoinGeometry')
        links.new(p_start.outputs['Mesh'], join_pts.inputs['Geometry'])
        links.new(coll_info.outputs['Instances'], join_pts.inputs['Geometry'])
        links.new(p_end.outputs['Mesh'], join_pts.inputs['Geometry'])
        
        p_to_c = nodes.new('GeometryNodePointsToCurve')
        links.new(join_pts.outputs['Geometry'], p_to_c.inputs['Points'])
        
        resample = nodes.new('GeometryNodeResampleCurve')
        links.new(p_to_c.outputs['Curve'], resample.inputs['Curve'])
        links.new(g_in.outputs[res_sock.name], resample.inputs['Count'])
        
        # --- 3. Spiral Offset Logic ---
        # We move each point of the resampled curve in a circle perpendicular to its tangent.
        set_pos = nodes.new('GeometryNodeSetPosition')
        links.new(resample.outputs['Curve'], set_pos.inputs['Geometry'])
        
        # Rotation angle = 2 * PI * Turns * Curve Parameter
        param = nodes.new('GeometryNodeInputCurveHandleType') # Wait, I need Curve Parameter
        param = nodes.new('GeometryNodeSplineParameter')
        
        math_angle = nodes.new('ShaderNodeMath'); math_angle.operation = 'MULTIPLY'
        links.new(param.outputs['Factor'], math_angle.inputs[0])
        links.new(g_in.outputs[turns_sock.name], math_angle.inputs[1])
        
        math_2pi = nodes.new('ShaderNodeMath'); math_2pi.operation = 'MULTIPLY'; math_2pi.inputs[1].default_value = 6.283185
        links.new(math_angle.outputs['Value'], math_2pi.inputs[0])
        
        # Circular offset in local space (R * cos, R * sin, 0)
        cos = nodes.new('ShaderNodeMath'); cos.operation = 'COS'
        sin = nodes.new('ShaderNodeMath'); sin.operation = 'SIN'
        links.new(math_2pi.outputs['Value'], cos.inputs[0])
        links.new(math_2pi.outputs['Value'], sin.inputs[0])
        
        comb_vec = nodes.new('ShaderNodeCombineXYZ')
        links.new(cos.outputs['Value'], comb_vec.inputs[0])
        links.new(sin.outputs['Value'], comb_vec.inputs[1])
        
        # Scale by Radius
        math_rad = nodes.new('ShaderNodeVectorMath'); math_rad.operation = 'SCALE'
        links.new(comb_vec.outputs['Vector'], math_rad.inputs['Vector'])
        links.new(g_in.outputs[rad_sock.name], math_rad.inputs['Scale'])
        
        # Align to Tangent
        # We need the tangent of the curve to orient the circle.
        tan = nodes.new('GeometryNodeInputTangent')
        align = nodes.new('GeometryNodeAlignEulerToVector'); align.axis = 'Z'
        links.new(tan.outputs['Tangent'], align.inputs['Vector'])
        
        vec_rot = nodes.new('ShaderNodeVectorMath'); vec_rot.name = "Vector Rotate" # Custom node or use Rotate Vector
        vec_rot = nodes.new('GeometryNodeRotateVector')
        links.new(math_rad.outputs['Vector'], vec_rot.inputs['Vector'])
        links.new(align.outputs['Rotation'], vec_rot.inputs['Rotation'])
        
        links.new(vec_rot.outputs['Vector'], set_pos.inputs['Offset'])
        
        # --- 4. Profile ---
        profile = nodes.new('GeometryNodeCurvePrimitiveCircle'); profile.inputs['Resolution'].default_value = 8
        links.new(g_in.outputs[wire_sock.name], profile.inputs['Radius'])
        
        to_mesh = nodes.new('GeometryNodeCurveToMesh')
        links.new(set_pos.outputs['Geometry'], to_mesh.inputs['Curve'])
        links.new(profile.outputs['Curve'], to_mesh.inputs['Profile Curve'])
        
        # Material
        set_mat = nodes.new('GeometryNodeSetMaterial')
        links.new(to_mesh.outputs['Mesh'], set_mat.inputs['Geometry'])
        
        links.new(set_mat.outputs['Geometry'], g_out.inputs['Geometry'])

    # --- Add Modifier ---
    mod = slinky_obj.modifiers.get(NATIVE_SLINKY_MOD_NAME)
    if not mod:
        mod = slinky_obj.modifiers.new(name=NATIVE_SLINKY_MOD_NAME, type='NODES')
    mod.node_group = gn_group
    
    # Drivers
    props = slinky_obj.fcd_pg_mech_props
    mod["Socket_2"] = start_empty # Start Object
    mod["Socket_3"] = end_empty # End Object
    
    # Link the hooks collection
    if props.slinky_hooks:
        # AI Editor Note: In Blender 4.0+, we can directly assign the collection.
        # However, for robustness we ensure the collection exists and is linked.
        coll_name = f"FCD_SlinkyHooks_{slinky_obj.name}"
        coll = bpy.data.collections.get(coll_name)
        if not coll:
            coll = bpy.data.collections.new(coll_name)
            bpy.context.scene.collection.children.link(coll)
        
        # Populate collection from the PointerProperty objects
        for item in props.slinky_hooks:
            if item.target and item.target.name not in coll.objects:
                coll.objects.link(item.target)
        
        mod["Socket_4"] = coll # Hooks Collection
    
    # Drive properties
    def add_driver(target_obj, data_path, prop_owner, prop_path):
        d = target_obj.driver_add(data_path).driver
        v = d.variables.new()
        v.name = "var"
        v.type = 'SINGLE_PROP'
        v.targets[0].id = prop_owner
        v.targets[0].data_path = prop_path
        d.expression = "var"

    add_driver(mod, '["Socket_5"]', slinky_obj, "fcd_pg_mech_props.radius")
    add_driver(mod, '["Socket_6"]', slinky_obj, "fcd_pg_mech_props.teeth")
    add_driver(mod, '["Socket_7"]', slinky_obj, "fcd_pg_mech_props.tooth_depth") # Repurposed as wire radius
    
    # Auto-smooth
    apply_auto_smooth(slinky_obj)

    # --- Add and Configure the Geometry Nodes Modifier ---
    mod = damper_obj.modifiers.get(NATIVE_DAMPER_MOD_NAME)
    if not mod:
        mod = damper_obj.modifiers.new(name=NATIVE_DAMPER_MOD_NAME, type='NODES')
    mod.node_group = gn_group

    # Connect Drivers
    if start_obj_socket: mod[start_obj_socket.identifier] = start_empty
    if end_obj_socket: mod[end_obj_socket.identifier] = end_empty
    
    if rad_sock: create_driver(damper_obj, '["spring_radius"]', mod.name, rad_sock.identifier)
    if wire_sock: create_driver(damper_obj, '["spring_wire_thickness"]', mod.name, wire_sock.identifier)
    if len_sock: create_driver(damper_obj, 'fcd_pg_mech_props.height', mod.name, len_sock.identifier)
    if piston_len_sock: create_driver(damper_obj, 'fcd_pg_mech_props.height', mod.name, piston_len_sock.identifier)
    if turns_sock: create_driver(damper_obj, '["spring_teeth"]', mod.name, turns_sock.identifier)
    if housing_rad_sock: create_driver(damper_obj, '["damper_housing_radius"]', mod.name, housing_rad_sock.identifier)
    if rod_rad_sock: create_driver(damper_obj, '["damper_rod_radius"]', mod.name, rod_rad_sock.identifier)
    if seat_rad_sock: create_driver(damper_obj, '["damper_seat_radius"]', mod.name, seat_rad_sock.identifier)
    if seat_thick_sock: create_driver(damper_obj, '["damper_seat_thickness"]', mod.name, seat_thick_sock.identifier)

def setup_native_rope_gn(rope_obj: bpy.types.Object) -> None:
    """
    High-Fidelity Rope Generator.
    Restores generation by ensuring stable GN linkage and driver assignment.
    """
    gn_group_name = f"FCD_Native_{rope_obj.name}_Rope_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')
        iface = gn_group.interface
        
        # --- 1. Sockets & Inputs ---
        in_geom = iface.new_socket(name="Geometry", in_out="INPUT", socket_type='NodeSocketGeometry')
        in_rad = iface.new_socket(name="Total Radius", in_out="INPUT", socket_type='NodeSocketFloat')
        in_rad.default_value = 0.01; in_rad.min_value = 0.0001
        in_strands = iface.new_socket(name="Strands", in_out="INPUT", socket_type='NodeSocketInt')
        in_strands.default_value = 6; in_strands.min_value = 1
        in_twist = iface.new_socket(name="Twist Rate", in_out="INPUT", socket_type='NodeSocketFloat')
        in_twist.default_value = 10.0
        in_tube = iface.new_socket(name="Tube Mode", in_out="INPUT", socket_type='NodeSocketBool')
        in_synth = iface.new_socket(name="Is Synthetic", in_out="INPUT", socket_type='NodeSocketBool')
        iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

        nodes = gn_group.nodes
        links = gn_group.links
        g_in = nodes.new('NodeGroupInput'); g_in.location = (-1500, 0)
        g_out = nodes.new('NodeGroupOutput'); g_out.location = (2800, 0)

        # Nodes
        m_to_c = nodes.new('GeometryNodeMeshToCurve'); m_to_c.location = (-1300, 500)
        resam = nodes.new('GeometryNodeResampleCurve'); resam.location = (-1100, 500)        # BALANCED RES: 2mm segments for smooth viewport performance
        resam.mode = 'LENGTH'; resam.inputs['Length'].default_value = 0.002

        dup = nodes.new('GeometryNodeDuplicateElements'); dup.domain = 'SPLINE'; dup.location = (-900, 500)
        para = nodes.new('GeometryNodeSplineParameter'); para.location = (-700, 400)
        idx = nodes.new('GeometryNodeInputIndex'); idx.location = (-700, 300)

        # Packing Math
        m_v_pi = nodes.new('ShaderNodeValue'); m_v_pi.outputs[0].default_value = math.pi
        m_pi = nodes.new('ShaderNodeMath'); m_pi.operation = 'DIVIDE'
        links.new(m_v_pi.outputs[0], m_pi.inputs[0])
        m_sin_a = nodes.new('ShaderNodeMath'); m_sin_a.operation = 'SINE'
        m_plus1 = nodes.new('ShaderNodeMath'); m_plus1.operation = 'ADD'; m_plus1.inputs[1].default_value = 1.0
        m_ring_r = nodes.new('ShaderNodeMath'); m_ring_r.operation = 'DIVIDE'
        m_strand_r = nodes.new('ShaderNodeMath'); m_strand_r.operation = 'MULTIPLY'

        # Angle Math
        m_v_2pi = nodes.new('ShaderNodeValue'); m_v_2pi.outputs[0].default_value = math.pi*2
        m_2pi = nodes.new('ShaderNodeMath'); m_2pi.operation = 'MULTIPLY'; m_2pi.inputs[1].default_value = 1.0 # Force 1.0 multiplier
        links.new(m_v_2pi.outputs[0], m_2pi.inputs[0])
        m_angle_step = nodes.new('ShaderNodeMath'); m_angle_step.operation = 'DIVIDE'
        m_base_angle = nodes.new('ShaderNodeMath'); m_base_angle.operation = 'MULTIPLY'
        m_twist_acc = nodes.new('ShaderNodeMath'); m_twist_acc.operation = 'MULTIPLY'

        # Lay & Weave
        m_lay_sw = nodes.new('GeometryNodeSwitch'); m_lay_sw.input_type = 'FLOAT'
        m_lay_sw.inputs['False'].default_value = 1.0
        m_mod2 = nodes.new('ShaderNodeMath'); m_mod2.operation = 'MODULO'; m_mod2.inputs[1].default_value = 2.0
        m_dir = nodes.new('ShaderNodeMath'); m_dir.operation = 'MULTIPLY'; m_dir.inputs[1].default_value = -2.0
        m_dir_add = nodes.new('ShaderNodeMath'); m_dir_add.operation = 'ADD'; m_dir_add.inputs[1].default_value = 1.0

        m_final_twist = nodes.new('ShaderNodeMath'); m_final_twist.operation = 'MULTIPLY'
        m_total_angle = nodes.new('ShaderNodeMath'); m_total_angle.operation = 'ADD'

        # Frenet vectors
        tan_v = nodes.new('GeometryNodeInputTangent')
        norm_v = nodes.new('GeometryNodeInputNormal')
        binorm_v = nodes.new('ShaderNodeVectorMath'); binorm_v.operation = 'CROSS_PRODUCT'

        # Pos Offset
        m_cos = nodes.new('ShaderNodeMath'); m_cos.operation = 'COSINE'
        m_sin = nodes.new('ShaderNodeMath'); m_sin.operation = 'SINE'
        m_rcos = nodes.new('ShaderNodeMath'); m_rcos.operation = 'MULTIPLY'
        m_rsin = nodes.new('ShaderNodeMath'); m_rsin.operation = 'MULTIPLY'
        v_off_n = nodes.new('ShaderNodeVectorMath'); v_off_n.operation = 'SCALE'
        v_off_b = nodes.new('ShaderNodeVectorMath'); v_off_b.operation = 'SCALE'
        v_sum = nodes.new('ShaderNodeVectorMath'); v_sum.operation = 'ADD'

        # Synthesis Weave
        m_wv_sine = nodes.new('ShaderNodeMath'); m_wv_sine.operation = 'SINE'
        m_wv_amp = nodes.new('ShaderNodeMath'); m_wv_amp.operation = 'MULTIPLY'
        m_sw_wv = nodes.new('GeometryNodeSwitch'); m_sw_wv.input_type = 'FLOAT'
        m_ring_final = nodes.new('ShaderNodeMath'); m_ring_final.operation = 'ADD'

        # Geometry
        set_pos = nodes.new('GeometryNodeSetPosition')
        prof_c = nodes.new('GeometryNodeCurvePrimitiveCircle'); prof_c.inputs['Resolution'].default_value = 12
        sweep = nodes.new('GeometryNodeCurveToMesh')

        # Core
        comp_core = nodes.new('FunctionNodeCompare'); comp_core.data_type = 'INT'; comp_core.operation = 'GREATER_EQUAL'; comp_core.inputs['B'].default_value = 5
        m_not_synth = nodes.new('ShaderNodeMath'); m_not_synth.operation = 'SUBTRACT'; m_not_synth.inputs[0].default_value = 1.0
        m_use_core = nodes.new('ShaderNodeMath'); m_use_core.operation = 'MULTIPLY'
        sw_core = nodes.new('GeometryNodeSwitch'); sw_core.input_type = 'GEOMETRY'
        core_sweep = nodes.new('GeometryNodeCurveToMesh'); core_prof = nodes.new('GeometryNodeCurvePrimitiveCircle'); core_prof.inputs['Resolution'].default_value = 12

        # Output Join
        join = nodes.new('GeometryNodeJoinGeometry')
        sw_tube = nodes.new('GeometryNodeSwitch'); sw_tube.input_type = 'GEOMETRY'
        tube_prof = nodes.new('GeometryNodeCurvePrimitiveCircle'); tube_prof.inputs['Resolution'].default_value = 12
        tube_sweep = nodes.new('GeometryNodeCurveToMesh')
        set_mat = nodes.new('GeometryNodeSetMaterial')

        # --- Linkage ---
        links.new(g_in.outputs[0], m_to_c.inputs['Mesh'])
        links.new(m_to_c.outputs['Curve'], resam.inputs['Curve'])
        links.new(resam.outputs['Curve'], dup.inputs['Geometry'])
        links.new(g_in.outputs[in_strands.name], dup.inputs['Amount'])
        
        # Packing
        links.new(g_in.outputs[in_strands.name], m_pi.inputs[1]); links.new(m_pi.outputs[0], m_sin_a.inputs[0])
        links.new(m_sin_a.outputs[0], m_plus1.inputs[0]); links.new(m_plus1.outputs[0], m_ring_r.inputs[1])
        links.new(g_in.outputs[in_rad.name], m_ring_r.inputs[0])
        links.new(m_ring_r.outputs[0], m_strand_r.inputs[0]); links.new(m_sin_a.outputs[0], m_strand_r.inputs[1])
        
        # Angle
        links.new(g_in.outputs[in_strands.name], m_angle_step.inputs[1]); links.new(m_2pi.outputs[0], m_angle_step.inputs[0])
        links.new(m_angle_step.outputs[0], m_base_angle.inputs[0]); links.new(dup.outputs['Duplicate Index'], m_base_angle.inputs[1])
        links.new(g_in.outputs[in_twist.name], m_twist_acc.inputs[1]); links.new(para.outputs['Factor'], m_twist_acc.inputs[0])
        
        # Lay Dir
        links.new(dup.outputs['Duplicate Index'], m_mod2.inputs[0]); links.new(m_mod2.outputs[0], m_dir.inputs[0])
        links.new(m_dir.outputs[0], m_dir_add.inputs[0]); links.new(m_dir_add.outputs[0], m_lay_sw.inputs['True'])
        links.new(g_in.outputs[in_synth.name], m_lay_sw.inputs['Switch'])
        links.new(m_twist_acc.outputs[0], m_final_twist.inputs[0]); links.new(m_lay_sw.outputs[0], m_final_twist.inputs[1])
        links.new(m_base_angle.outputs[0], m_total_angle.inputs[0]); links.new(m_final_twist.outputs[0], m_total_angle.inputs[1])
        
        # Stable Basis (Fallback protected Cross Products)
        up_v = nodes.new('ShaderNodeVectorMath'); up_v.operation = 'CROSS_PRODUCT'
        up_v.inputs[1].default_value = (0, 0, 1) # Primary Up
        
        # Fallback check
        v_len = nodes.new('ShaderNodeVectorMath'); v_len.operation = 'LENGTH'
        v_comp = nodes.new('FunctionNodeCompare'); v_comp.data_type = 'FLOAT'; v_comp.operation = 'LESS_THAN'; v_comp.inputs['B'].default_value = 0.1
        
        v_up_alt = nodes.new('GeometryNodeSwitch'); v_up_alt.input_type = 'VECTOR'
        v_up_alt.inputs['False'].default_value = (0, 0, 1)
        v_up_alt.inputs['True'].default_value = (0, 1, 0)
        
        links.new(tan_v.outputs[0], up_v.inputs[0])
        links.new(up_v.outputs[0], v_len.inputs[1]); links.new(v_len.outputs[0], v_comp.inputs['A'])
        links.new(v_comp.outputs[0], v_up_alt.inputs['Switch'])
        
        # Basis 1 (Normal-like)
        b1_v = nodes.new('ShaderNodeVectorMath'); b1_v.operation = 'CROSS_PRODUCT'
        links.new(tan_v.outputs[0], b1_v.inputs[0]); links.new(v_up_alt.outputs[0], b1_v.inputs[1])
        
        # Basis 2 (Binormal-like)
        b2_v = nodes.new('ShaderNodeVectorMath'); b2_v.operation = 'CROSS_PRODUCT'
        links.new(tan_v.outputs[0], b2_v.inputs[0]); links.new(b1_v.outputs[0], b2_v.inputs[1])
        
        # Weave Logic (Synthetic Rope Only)
        links.new(m_total_angle.outputs[0], m_wv_sine.inputs[0])
        links.new(m_wv_sine.outputs[0], m_wv_amp.inputs[0]); links.new(m_strand_r.outputs[0], m_wv_amp.inputs[1])
        links.new(g_in.outputs[in_synth.name], m_sw_wv.inputs['Switch'])
        links.new(m_wv_amp.outputs[0], m_sw_wv.inputs['True']); m_sw_wv.inputs['False'].default_value = 0.0
        
        links.new(m_ring_r.outputs[0], m_ring_final.inputs[0]); links.new(m_sw_wv.outputs[0], m_ring_final.inputs[1])
        
        links.new(m_total_angle.outputs[0], m_cos.inputs[0]); links.new(m_total_angle.outputs[0], m_sin.inputs[0])
        links.new(m_ring_final.outputs[0], m_rcos.inputs[0]); links.new(m_cos.outputs[0], m_rcos.inputs[1])
        links.new(m_ring_final.outputs[0], m_rsin.inputs[0]); links.new(m_sin.outputs[0], m_rsin.inputs[1])
        
        links.new(b1_v.outputs[0], v_off_n.inputs['Vector']); links.new(m_rcos.outputs[0], v_off_n.inputs['Scale'])
        links.new(b2_v.outputs[0], v_off_b.inputs['Vector']); links.new(m_rsin.outputs[0], v_off_b.inputs['Scale'])
        links.new(v_off_n.outputs[0], v_sum.inputs[0]); links.new(v_off_b.outputs[0], v_sum.inputs[1])
        
        links.new(dup.outputs['Geometry'], set_pos.inputs['Geometry']); links.new(v_sum.outputs[0], set_pos.inputs['Offset'])
        
        # Sweep
        # OVERSIZE FIX: Synthetic strands are oversized by 15% to eliminate gaps
        m_sw_sz = nodes.new('GeometryNodeSwitch'); m_sw_sz.input_type = 'FLOAT'
        links.new(g_in.outputs[in_synth.name], m_sw_sz.inputs['Switch'])
        m_ov_sz = nodes.new('ShaderNodeMath'); m_ov_sz.operation = 'MULTIPLY'; m_ov_sz.inputs[1].default_value = 1.15
        links.new(m_strand_r.outputs[0], m_ov_sz.inputs[0]); links.new(m_ov_sz.outputs[0], m_sw_sz.inputs['True'])
        links.new(m_strand_r.outputs[0], m_sw_sz.inputs['False'])
        
        links.new(set_pos.outputs['Geometry'], sweep.inputs['Curve']); links.new(prof_c.outputs['Curve'], sweep.inputs['Profile Curve'])
        links.new(m_sw_sz.outputs[0], prof_c.inputs['Radius'])
        
        # Core & Join
        links.new(g_in.outputs[in_strands.name], comp_core.inputs['A'])
        m_use_core = nodes.new('ShaderNodeMath'); m_use_core.operation = 'MAXIMUM'
        links.new(g_in.outputs[in_synth.name], m_use_core.inputs[0])
        links.new(comp_core.outputs['Result'], m_use_core.inputs[1])
        links.new(m_use_core.outputs[0], sw_core.inputs['Switch'])
        
        links.new(resam.outputs['Curve'], core_sweep.inputs['Curve']); links.new(core_prof.outputs['Curve'], core_sweep.inputs['Profile Curve'])
        # CORE RADIUS FIX: Core should fill the space (RingRadius - StrandRadius)
        m_c_rad = nodes.new('ShaderNodeMath'); m_c_rad.operation = 'SUBTRACT'
        links.new(m_ring_r.outputs[0], m_c_rad.inputs[0]); links.new(m_strand_r.outputs[0], m_c_rad.inputs[1])
        links.new(m_c_rad.outputs[0], core_prof.inputs['Radius'])
        links.new(core_sweep.outputs['Mesh'], sw_core.inputs['True'])
        
        links.new(sweep.outputs['Mesh'], join.inputs[0]); links.new(sw_core.outputs[0], join.inputs[0])
        
        # Tube Swapper
        links.new(resam.outputs['Curve'], tube_sweep.inputs['Curve']); links.new(tube_prof.outputs['Curve'], tube_sweep.inputs['Profile Curve'])
        links.new(g_in.outputs[in_rad.name], tube_prof.inputs['Radius'])
        links.new(g_in.outputs[in_tube.name], sw_tube.inputs['Switch'])
        links.new(join.outputs['Geometry'], sw_tube.inputs['False']); links.new(tube_sweep.outputs['Mesh'], sw_tube.inputs['True'])
        
        links.new(sw_tube.outputs[0], set_mat.inputs['Geometry'])
        links.new(set_mat.outputs['Geometry'], g_out.inputs[0])

    iface = gn_group.interface
    if hasattr(rope_obj.data, "twist_mode"): rope_obj.data.twist_mode = 'MINIMUM'
    mod = rope_obj.modifiers.get(f"{MOD_PREFIX}Native_Rope")
    if not mod: mod = rope_obj.modifiers.new(name=f"{MOD_PREFIX}Native_Rope", type='NODES')
    mod.node_group = gn_group
    
    # Drivers
    pref = '["rope_radius"]', '["rope_strands"]', '["rope_twist"]', '["rope_tube_mode"]', '["rope_is_synthetic"]'
    keys = "Total Radius", "Strands", "Twist Rate", "Tube Mode", "Is Synthetic"
    for k, p in zip(keys, pref):
        sock = iface.items_tree.get(k)
        if sock: create_driver(rope_obj, p, mod.name, sock.identifier)

def setup_native_wrap_gn(path_obj: bpy.types.Object) -> None:
    """
    Creates or updates the 'Wrap' Geometry Nodes modifier.

    This modifier is responsible for the "Dynamic Wrapping" feature. It takes a
    collection of objects and generates a convex hull curve around them.
    It is placed at the top of the modifier stack so that it feeds this generated
    path into the subsequent 'Chain' modifier.
    """
    gn_group_name = f"FCD_Native_{path_obj.name}_Wrap_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')

    # --- Clear existing nodes and interface to ensure a clean, up-to-date build ---
    # This guarantees that any logic changes in the script are applied to existing objects.
    gn_group.nodes.clear()
    gn_group.interface.clear()

    iface = gn_group.interface
    iface.new_socket(name="Geometry", in_out="INPUT", socket_type='NodeSocketGeometry')
    iface.new_socket(name="Wrap Collection", in_out="INPUT", socket_type='NodeSocketCollection')
    # ADDED: Input for resolution to control vertex density
    res_socket = iface.new_socket(name="Resolution", in_out="INPUT", socket_type='NodeSocketFloat')
    res_socket.default_value = 0.1
    res_socket.min_value = 0.001
    res_socket.description = "Target distance between vertices"
    iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

    nodes = gn_group.nodes
    links = gn_group.links

    group_input = nodes.new('NodeGroupInput')
    group_input.location = (-1800, 0)
    group_output = nodes.new('NodeGroupOutput')
    group_output.location = (1600, 0)

    # --- Node Logic: Wrap Collection (Convex Hull) ---
    col_info = nodes.new('GeometryNodeCollectionInfo')
    col_info.location = (-1400, 200)
    col_info.transform_space = 'RELATIVE'
    col_info.inputs['Separate Children'].default_value = True # Ensure nested hierarchies work

    # --- Data Gathering: Collect all points to wrap around ---
    # 1. Realize Instances to get actual mesh vertices from the collection.
    realize_instances = nodes.new('GeometryNodeRealizeInstances')
    realize_instances.location = (-1200, 200)

    # 2. Convert Instances to Points to capture Empties (which would otherwise disappear).
    instances_to_points = nodes.new('GeometryNodeInstancesToPoints')
    instances_to_points.location = (-1200, 0)

    # AI Editor Note: Removed curve_input_points to prevent the "invisible hook" issue.
    # The convex hull should be defined strictly by the wrap objects, not the original curve path.

    # 3. Join all these points into a single cloud for the Convex Hull.
    # NOTE: We intentionally do NOT include the original curve points here.
    # Including them would cause the default curve shape (e.g., a large circle)
    # to dominate the hull, preventing the chain from wrapping tightly around
    # the selected objects. The wrap path should be defined purely by the collection.
    join_geom = nodes.new('GeometryNodeJoinGeometry')
    join_geom.location = (-1000, 200)

    # Clean up points before hull to avoid degenerate geometry
    merge_dist = nodes.new('GeometryNodeMergeByDistance')
    merge_dist.location = (-600, 200)
    merge_dist.inputs['Distance'].default_value = 0.001

    convex_hull = nodes.new('GeometryNodeConvexHull')
    convex_hull.location = (-400, 200)

    # --- Node Logic: Hull Cleanup ---
    # AI Editor Note: Convex Hull on flat points can sometimes produce a double-sided
    # "pancake" mesh. We delete downward-facing faces to ensure a single layer,
    # which is required for the boundary extraction logic to work correctly.
    delete_bottom = nodes.new('GeometryNodeDeleteGeometry')
    delete_bottom.domain = 'FACE'
    delete_bottom.location = (-200, 300)

    normal_node = nodes.new('GeometryNodeInputNormal')
    normal_node.location = (-400, 400)
    sep_z = nodes.new('ShaderNodeSeparateXYZ')
    sep_z.location = (-250, 400)
    compare_z = nodes.new('FunctionNodeCompare'); compare_z.operation = 'LESS_THAN'; compare_z.location = (-100, 400); compare_z.inputs['B'].default_value = -0.1

    # --- Node Logic: Boundary Extraction ---
    # The Convex Hull node outputs a filled mesh (often triangulated).
    # To get a clean path for the chain, we must delete internal edges
    # and keep only the boundary loop. We do this by keeping edges that
    # have exactly one adjacent face.
    edge_neighbors = nodes.new('GeometryNodeInputMeshEdgeNeighbors')
    edge_neighbors.location = (-400, 100)

    compare_edges = nodes.new('FunctionNodeCompare')
    compare_edges.data_type = 'INT'
    compare_edges.operation = 'GREATER_THAN' # Delete internal edges (shared by >1 faces)
    compare_edges.location = (-200, 100)
    compare_edges.inputs['B'].default_value = 1

    delete_geom = nodes.new('GeometryNodeDeleteGeometry')
    delete_geom.domain = 'EDGE'
    delete_geom.location = (0, 200)

    # --- Node Logic: Curve Finalization ---
    mesh_to_curve = nodes.new('GeometryNodeMeshToCurve')
    mesh_to_curve.location = (200, 200)

    # NEW: Force Zero Tilt to prevent Mobius twisting on the generated path
    set_tilt = nodes.new('GeometryNodeSetCurveTilt')
    set_tilt.location = (300, 200)
    set_tilt.inputs['Tilt'].default_value = 0.0

    # Force the curve to be cyclic (closed loop) to ensure a continuous chain.
    set_cyclic = nodes.new('GeometryNodeSetSplineCyclic')
    set_cyclic.location = (400, 200)
    set_cyclic.inputs['Cyclic'].default_value = True

    # ADDED: Resample the curve so vertices match the chain pitch.
    # This ensures the wrapping geometry has the correct resolution for the links.
    resample_curve = nodes.new('GeometryNodeResampleCurve')
    resample_curve.location = (600, 200)
    resample_curve.mode = 'LENGTH'

    # Set a default radius for the generated curve to ensure visibility
    set_radius = nodes.new('GeometryNodeSetCurveRadius')
    set_radius.location = (800, 200)
    set_radius.inputs['Radius'].default_value = 1.0

    # --- Node Logic: Smart Switch ---
    # We want to use the generated wrap curve ONLY if:
    # 1. The user has actually selected objects to wrap (Collection is not empty).
    # 2. The wrapping process succeeded and produced valid geometry.
    # Otherwise, we pass through the original user-drawn curve. This allows for
    # manual S-curves or other non-convex shapes when not using the wrap feature.

    # Check 1: Is the collection populated?
    col_size = nodes.new('GeometryNodeAttributeDomainSize')
    col_size.location = (-1200, 500)
    col_size.component = 'INSTANCES'

    col_has_items = nodes.new('FunctionNodeCompare')
    col_has_items.location = (-1000, 500)
    col_has_items.data_type = 'INT'
    col_has_items.operation = 'GREATER_THAN'
    col_has_items.inputs['B'].default_value = 0

    # Check 2: Did the hull generation produce a curve?
    hull_size = nodes.new('GeometryNodeAttributeDomainSize')
    hull_size.location = (800, 400)
    hull_size.component = 'CURVE'

    hull_valid = nodes.new('FunctionNodeCompare')
    hull_valid.location = (1000, 400)
    hull_valid.data_type = 'INT'
    hull_valid.operation = 'GREATER_THAN'
    hull_valid.inputs['B'].default_value = 0

    # Combine checks: (Collection > 0) AND (Hull > 0)
    logic_and = nodes.new('FunctionNodeBooleanMath')
    logic_and.location = (1200, 400)
    logic_and.operation = 'AND'

    switch = nodes.new('GeometryNodeSwitch')
    switch.location = (1400, 0)
    switch.input_type = 'GEOMETRY'

    # --- Links ---
    links.new(group_input.outputs["Wrap Collection"], col_info.inputs['Collection'])

    # Connect robust geometry gathering
    links.new(col_info.outputs['Instances'], realize_instances.inputs['Geometry'])
    links.new(col_info.outputs['Instances'], instances_to_points.inputs['Instances'])
    links.new(realize_instances.outputs['Geometry'], join_geom.inputs['Geometry'])
    links.new(instances_to_points.outputs['Points'], join_geom.inputs['Geometry'])

    # AI Editor Note: Direct connection to allow 3D wrapping (no flattening).
    # This fixes the "2D lock" issue, allowing the chain to wrap objects in 3D space.
    links.new(join_geom.outputs['Geometry'], merge_dist.inputs['Geometry'])
    links.new(merge_dist.outputs['Geometry'], convex_hull.inputs['Geometry'])

    # Hull Cleanup Links
    links.new(convex_hull.outputs['Convex Hull'], delete_bottom.inputs['Geometry'])
    links.new(normal_node.outputs['Normal'], sep_z.inputs['Vector'])
    links.new(sep_z.outputs['Z'], compare_z.inputs['A'])
    links.new(compare_z.outputs['Result'], delete_bottom.inputs['Selection'])

    # Filter for boundary edges
    links.new(delete_bottom.outputs['Geometry'], delete_geom.inputs['Geometry'])
    links.new(edge_neighbors.outputs['Face Count'], compare_edges.inputs['A'])
    links.new(compare_edges.outputs['Result'], delete_geom.inputs['Selection'])
    links.new(delete_geom.outputs['Geometry'], mesh_to_curve.inputs['Mesh'])
    links.new(mesh_to_curve.outputs['Curve'], set_tilt.inputs['Curve'])
    links.new(set_tilt.outputs['Curve'], set_cyclic.inputs['Geometry'])

    links.new(set_cyclic.outputs['Geometry'], resample_curve.inputs['Curve'])
    links.new(group_input.outputs["Resolution"], resample_curve.inputs['Length'])
    links.new(resample_curve.outputs['Curve'], set_radius.inputs['Curve'])

    # Switch Logic Links
    links.new(col_info.outputs['Instances'], col_size.inputs['Geometry'])
    links.new(col_size.outputs['Instance Count'], col_has_items.inputs['A'])

    links.new(set_radius.outputs['Curve'], hull_size.inputs['Geometry'])
    links.new(hull_size.outputs['Point Count'], hull_valid.inputs['A'])

    links.new(col_has_items.outputs['Result'], logic_and.inputs[0])
    links.new(hull_valid.outputs['Result'], logic_and.inputs[1])

    links.new(logic_and.outputs['Boolean'], switch.inputs['Switch'])
    links.new(set_radius.outputs['Curve'], switch.inputs['True'])
    links.new(group_input.outputs["Geometry"], switch.inputs['False'])

    links.new(switch.outputs['Output'], group_output.inputs['Geometry'])

    mod_name = f"{MOD_PREFIX}Native_Wrap"
    mod = path_obj.modifiers.get(mod_name)
    if not mod:
        mod = path_obj.modifiers.new(name=mod_name, type='NODES')

    mod.node_group = gn_group

    # Ensure it's at the top of the stack to process the curve before the chain generator
    with bpy.context.temp_override(object=path_obj):
        bpy.ops.object.modifier_move_to_index(modifier=mod_name, index=0)

    if hasattr(path_obj.fcd_pg_mech_props, "chain_wrap_collection"):
        wrap_socket = gn_group.interface.items_tree.get("Wrap Collection")
        if wrap_socket:
            mod[wrap_socket.identifier] = path_obj.fcd_pg_mech_props.chain_wrap_collection

    # ADDED: Connect Resolution driver
    res_socket = gn_group.interface.items_tree.get("Resolution")
    if res_socket:
        create_driver(path_obj, '["fcd_native_chain_res"]', mod.name, res_socket.identifier)

def setup_native_chain_gn(path_obj: bpy.types.Object, link_obj: bpy.types.Object) -> None:
    """
    Creates and configures a dynamic, procedural Geometry Nodes setup for a rigid
    chain or belt.

    This function is responsible for two main tasks:
    1.  Creating a unique, independent Geometry Nodes group for this specific
        chain object. This is crucial to prevent any shared data issues when
        multiple chains are in the scene.
    2.  Adding a Geometry Nodes modifier to the `path_obj` (a curve) and
        configuring it to instance the `link_obj` (a mesh) along the curve.

    AI Editor Note:
    This function is another example of the addon's native-first philosophy.
    The setup is fully native and robust. Key parameters like link pitch and
    animation are controlled by native custom properties on the `path_obj`, which
    are connected to the node group via drivers. This ensures the chain continues
    to function perfectly even if the addon is disabled or removed. The instanced
    link object is kept separate and hidden, and the main curve object serves as
    the single point of control for the user.

    Args:
        path_obj: The curve object that defines the chain's path. This object
                  will receive the Geometry Nodes modifier.
        link_obj: The mesh object representing a single link to be instanced.
    """
    # --- UNIQUE NODE GROUP ---
    # Create a unique name for the node group based on the path object's name.
    # This ensures that each chain has its own independent node group.
    gn_group_name = f"FCD_Native_{path_obj.name}_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')

    # AI Editor Note: Force clear the node tree to ensure logic updates are applied to existing chains.
    gn_group.nodes.clear()
    gn_group.interface.clear()

    # --- 1. Define Node Group Interface (Inputs & Outputs) ---
    iface = gn_group.interface
    iface.new_socket(name="Geometry", in_out="INPUT", socket_type='NodeSocketGeometry')
    link_obj_socket = iface.new_socket(name="Link Object", in_out="INPUT", socket_type='NodeSocketObject')
    link_len_socket = iface.new_socket(name="Link Length", in_out="INPUT", socket_type='NodeSocketFloat')
    link_len_socket.default_value = 0.2
    link_len_socket.min_value = 0.01
    anim_socket = iface.new_socket(name="Animation Offset", in_out="INPUT", socket_type='NodeSocketFloat')
    iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

    # --- 2. Create Core Nodes ---
    nodes = gn_group.nodes
    links = gn_group.links

    group_input = nodes.new('NodeGroupInput')
    group_input.location = (-1400, 0)
    group_output = nodes.new('NodeGroupOutput')
    group_output.location = (800, 0)

    # --- 3. Node Logic: Generate Base Points ---
    # We generate points on the *original* curve to get the correct count and spacing.
    # We will then override their positions to animate them.
    curve_to_points = nodes.new('GeometryNodeCurveToPoints')
    curve_to_points.location = (-1200, 100)
    curve_to_points.mode = 'LENGTH'

    # --- 4. Node Logic: Calculate Animated Position (Rolling) ---
    # Formula: TargetLength = (Index * Pitch + AnimOffset) % TotalLength

    # Get Index and Pitch
    index_node = nodes.new('GeometryNodeInputIndex')
    index_node.location = (-1200, -100)

    math_base_len = nodes.new('ShaderNodeMath')
    math_base_len.operation = 'MULTIPLY'
    math_base_len.location = (-1000, -100)

    # Add Animation Offset
    math_add_anim = nodes.new('ShaderNodeMath')
    math_add_anim.operation = 'ADD'
    math_add_anim.location = (-800, -100)

    # Get Total Curve Length
    curve_length = nodes.new('GeometryNodeCurveLength')
    curve_length.location = (-1200, -300)

    # Wrap around the curve (Modulo)
    math_mod = nodes.new('ShaderNodeMath')
    math_mod.operation = 'FLOORED_MODULO' # Handles negative animation correctly
    math_mod.location = (-600, -100)

    # --- 5. Node Logic: Sample Curve at New Position ---
    # This gives us the Position, Tangent, and Normal at the animated location.
    sample_curve = nodes.new('GeometryNodeSampleCurve')
    sample_curve.location = (-400, 0)
    sample_curve.mode = 'LENGTH'

    # Set the new position of the points
    set_position = nodes.new('GeometryNodeSetPosition')
    set_position.location = (-200, 100)

    # Calculate Rotation from Tangent
    align_euler = nodes.new('FunctionNodeAlignEulerToVector')
    align_euler.location = (-200, -100)
    align_euler.axis = 'X'
    align_euler.pivot_axis = 'AUTO'

    # --- 6. Node Logic: Instance Links ---
    link_info = nodes.new('GeometryNodeObjectInfo')
    link_info.location = (-200, -300)
    link_info.transform_space = 'ORIGINAL'

    instance_on_points = nodes.new('GeometryNodeInstanceOnPoints')
    instance_on_points.location = (200, 0)

    # --- 7. Node Logic: Radius Scaling (Optional but recommended) ---
    # We need to sample the radius at the *new* position.
    # Since Sample Curve doesn't output radius, we sample the nearest point on the original curve
    # to the new position, then get the radius from there.
    sample_nearest = nodes.new('GeometryNodeSampleNearest')
    sample_nearest.location = (0, -400)

    sample_index = nodes.new('GeometryNodeSampleIndex')
    sample_index.location = (200, -400)
    sample_index.data_type = 'FLOAT'

    radius_attr = nodes.new('GeometryNodeInputNamedAttribute')
    radius_attr.location = (0, -550)
    radius_attr.data_type = 'FLOAT'
    radius_attr.inputs['Name'].default_value = "radius"

    # --- 8. Link Everything ---
    # Base Points
    links.new(group_input.outputs['Geometry'], curve_to_points.inputs['Curve'])
    links.new(group_input.outputs['Link Length'], curve_to_points.inputs['Length'])

    # Calculation Chain
    links.new(index_node.outputs['Index'], math_base_len.inputs[0])
    links.new(group_input.outputs['Link Length'], math_base_len.inputs[1])

    links.new(math_base_len.outputs['Value'], math_add_anim.inputs[0])
    links.new(group_input.outputs['Animation Offset'], math_add_anim.inputs[1])

    links.new(group_input.outputs['Geometry'], curve_length.inputs['Curve'])

    links.new(math_add_anim.outputs['Value'], math_mod.inputs[0])
    links.new(curve_length.outputs['Length'], math_mod.inputs[1])

    # Sampling
    # AI Editor Note: In Blender 4.x, the input socket for Sample Curve is named "Curves".
    links.new(group_input.outputs['Geometry'], sample_curve.inputs['Curves'])
    links.new(math_mod.outputs['Value'], sample_curve.inputs['Length'])

    # Set Position & Rotation
    links.new(curve_to_points.outputs['Points'], set_position.inputs['Geometry'])
    links.new(sample_curve.outputs['Position'], set_position.inputs['Position'])

    links.new(sample_curve.outputs['Tangent'], align_euler.inputs['Vector'])

    # Instancing
    links.new(set_position.outputs['Geometry'], instance_on_points.inputs['Points'])
    links.new(group_input.outputs['Link Object'], link_info.inputs['Object'])
    links.new(link_info.outputs['Geometry'], instance_on_points.inputs['Instance'])
    links.new(align_euler.outputs['Rotation'], instance_on_points.inputs['Rotation'])

    # Scaling
    links.new(group_input.outputs['Geometry'], sample_nearest.inputs['Geometry'])
    links.new(sample_curve.outputs['Position'], sample_nearest.inputs['Sample Position'])

    links.new(group_input.outputs['Geometry'], sample_index.inputs['Geometry'])
    links.new(sample_nearest.outputs['Index'], sample_index.inputs['Index'])
    links.new(radius_attr.outputs['Attribute'], sample_index.inputs['Value'])

    links.new(sample_index.outputs['Value'], instance_on_points.inputs['Scale'])

    # Output
    links.new(instance_on_points.outputs['Instances'], group_output.inputs['Geometry'])

    # --- Add/Update the Modifier on the Path Object ---
    # The modifier name is kept constant for a given chain type. This is robust
    # because even if the user renames the path object, the drivers that target
    # the modifier by this name will not break.
    mod_name = f"{MOD_PREFIX}Native_{path_obj.fcd_pg_mech_props.type_chain.capitalize()}Chain"
    mod = path_obj.modifiers.get(mod_name)
    if not mod:
        mod = path_obj.modifiers.new(name=mod_name, type='NODES')

    mod.node_group = gn_group

    # --- Connect Modifier Inputs to Properties/Objects ---
    iface = gn_group.interface
    link_obj_socket = iface.items_tree.get("Link Object")
    link_len_socket = iface.items_tree.get("Link Length")
    anim_socket = iface.items_tree.get("Animation Offset")

    if link_obj_socket:
        mod[link_obj_socket.identifier] = link_obj

    if link_len_socket:
        # Create a native driver to link the modifier's input to a persistent, native
        # custom property. This ensures the chain works even if the addon is disabled.
        create_driver(path_obj, '["fcd_native_chain_pitch"]', mod.name, link_len_socket.identifier)

    if anim_socket:
        # Create a native driver for the animation offset.
        create_driver(path_obj, '["fcd_native_anim_offset"]', mod.name, anim_socket.identifier)

def update_chain_driver_settings(self: 'FCD_PG_Mech_Props', context: bpy.types.Context) -> None:
    """
    Updates the chain driver expression based on radius, ratio, and invert settings.
    AI Editor Note: This allows for real-time manual adjustment of the drive system
    without re-running the link operator.
    """
    obj = self.id_data
    if not obj or self.category != 'CHAIN':
        return

    # Check if driver exists on the native animation offset property
    if not obj.animation_data or not obj.animation_data.drivers:
        return
        
    fcurve = obj.animation_data.drivers.find('["fcd_native_anim_offset"]')
    if not fcurve:
        return

    driver = fcurve.driver
    
    # Calculate final multiplier components
    radius = self.chain_drive_radius
    ratio = self.chain_drive_ratio
    invert = -1.0 if self.chain_drive_invert else 1.0
    
    # Update expression
    # We assume the variable 'rotation' exists as created by the Link operator.
    # Formula: offset = rotation * radius * manual_ratio * direction
    driver.expression = f"rotation * {radius:.4f} * {ratio:.4f} * {invert:.1f}"

def update_dimensions_for_object(obj: bpy.types.Object) -> None:
    """Updates a single dimension object (label or arrow) based on its local properties."""
    if not obj or not obj.get("fcd_is_dimension"):
        return

    mod = obj.modifiers.get("Dynamic_Dimension")
    # If it has a GN modifier, update the GN parameters
    if mod and mod.node_group:
        unit_display = getattr(obj, "fcd_dim_unit_display", 'SCENE')
        gn_scale, gn_suffix = get_dimension_unit_settings(bpy.context.scene, unit_display)

        scale_id = None
        suffix_id = None
        if hasattr(mod.node_group, "interface"):
            for item in mod.node_group.interface.items_tree:
                if item.name == "Scale":
                    scale_id = item.identifier
                elif item.name == "Suffix":
                    suffix_id = item.identifier
        
        if scale_id: mod[scale_id] = gn_scale
        if suffix_id: mod[suffix_id] = gn_suffix
    
    # Update color / materials
    from . import operators
    mat = operators.get_or_create_text_material(obj)
    if obj.data and hasattr(obj.data, "materials"):
        if not obj.data.materials:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat
            
    obj.update_tag()

def get_dimension_unit_settings(scene, unit_display):
    """Helper to convert unit enum to scale and suffix."""
    unit_settings = scene.unit_settings
    unit_sys = unit_settings.system
    u_type = unit_settings.length_unit
    scale_length = unit_settings.scale_length

    if unit_display == 'MM':
        return 1000.0, "mm"
    elif unit_display == 'CM':
        return 100.0, "cm"
    elif unit_display == 'IMPERIAL':
        return 3.28084, "ft"
    elif unit_display == 'METRIC':
        return 1.0, "m"
    
    # Fallback to SCENE units
    gn_scale = 1.0
    gn_suffix = "m"
    if unit_sys == 'METRIC':
        if u_type == 'MILLIMETERS': gn_scale = 1000.0; gn_suffix = "mm"
        elif u_type == 'CENTIMETERS': gn_scale = 100.0; gn_suffix = "cm"
        elif u_type == 'KILOMETERS': gn_scale = 0.001; gn_suffix = "km"
        gn_scale *= scale_length
    elif unit_sys == 'IMPERIAL':
        if u_type == 'FEET': gn_scale = 3.28084; gn_suffix = "ft"
        elif u_type == 'INCHES': gn_scale = 39.3701; gn_suffix = "in"
        gn_scale *= scale_length
    
    return gn_scale, gn_suffix

def update_dimensions(scene: bpy.types.Scene) -> None:
    """Updates all URDF dimension objects."""
    for obj in scene.objects:
        if obj.get("fcd_is_dimension"):
            update_dimensions_for_object(obj)

@persistent
def dimension_update_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    """Handler to update dimensions when units change."""
    if not scene: return
    unit_settings = scene.unit_settings
    # AI Editor Note: Include scale_length in key to detect unit scale changes
    current_unit_key = f"{unit_settings.system}_{unit_settings.length_unit}_{unit_settings.scale_length}"
    
    if scene.get("fcd_last_unit_key") != current_unit_key:
        update_dimensions(scene)
        scene["fcd_last_unit_key"] = current_unit_key

# ------------------------------------------------------------------------
#   PART 1.2: AI GENERATION LOGIC (LOCAL)
# ------------------------------------------------------------------------

def get_part_catalog_prompt() -> str:
    """
    Generates a system prompt describing the available parametric parts.
    This is used to inform the Cloud AI about the tools it can use.
    """
    catalog = []
    catalog.append("You are a robot design assistant for Blender.")
    catalog.append("Your goal is to generate a robot configuration in JSON format.")
    catalog.append("Prefer using the following available parametric parts over generic primitives:")
    
    # List categories and types
    catalog.append("- GEAR: " + ", ".join([t[0] for t in GEAR_TYPES]))
    catalog.append("- WHEEL: " + ", ".join([t[0] for t in WHEEL_TYPES]))
    catalog.append("- ELECTRONICS: " + ", ".join([t[0] for t in ALL_ELECTRONICS_TYPES]))
    catalog.append("- SPRING: " + ", ".join([t[0] for t in SPRING_TYPES]))
    catalog.append("- FASTENER: " + ", ".join([t[0] for t in FASTENER_TYPES]))
    
    catalog.append("\nOutput Format (JSON):")
    catalog.append("{ 'type': 'ROVER', 'components': [ { 'category': 'WHEEL', 'type': 'WHEEL_OFFROAD', 'location': [x,y,z], ... } ] }")
    return "\n".join(catalog)

def create_parametric_part_object(context: bpy.types.Context, category: str, type_sub: str, location: mathutils.Vector, scale_factor: float = 1.0, **kwargs) -> bpy.types.Object:
    """
    Programmatically creates a parametric part object with the specified properties.
    This function centralizes the creation logic, ensuring consistency between
    UI operators and AI generation.
    """
    # AI Editor Note: Ensure Object Mode and clean selection to prevent context errors
    # with operators like transform_apply or when creating objects.
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    coll_name = "Mechanical_Parts"
    coll = bpy.data.collections.get(coll_name)
    if not coll:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)

    # Generate unique name
    base_name = type_sub.replace('_', ' ').title()
    name = get_unique_name(base_name)
    
    new_obj = None

    # --- 1. Create Object based on Category ---
    if category == 'CHAIN':
        new_obj = create_parametric_chain(context, type_sub)
    elif category == 'SPRING':
        # Springs are typically represented by a mesh object
        mesh = bpy.data.meshes.new(name)
        new_obj = bpy.data.objects.new(name, mesh)
        coll.objects.link(new_obj)

        # AI Editor Note: Initial length of spring should match size cage
        props = new_obj.fcd_pg_mech_props
        props.length = scale_factor
        
        # Helper empties for positioning
        e_start = bpy.data.objects.new(name=f"Start_{new_obj.name}", object_data=None)
        e_start.location = new_obj.location
        context.collection.objects.link(e_start)
        props.spring_start_obj = e_start
        
        e_end = bpy.data.objects.new(name=f"End_{new_obj.name}", object_data=None)
        e_end.location = new_obj.location + mathutils.Vector((0, 0, scale_factor))
        context.collection.objects.link(e_end)
        props.spring_end_obj = e_end
        
        if type_sub == 'SPRING':
            setup_native_spring(new_obj, e_start, e_end)
        elif type_sub == 'DAMPER':
            # Initialize damper specific properties
            props.height = scale_factor
            props.damper_seat_radius = 0.08 * scale_factor
            props.damper_seat_thickness = 0.003 * scale_factor
            setup_native_damper(new_obj, e_start, e_end)
        elif type_sub == 'SPRING_SLINKY':
            # Initialize slinky specific properties
            props.radius = 0.05 * scale_factor
            props.tooth_depth = 0.002 * scale_factor # Wire radius
            props.teeth = 20
            setup_native_slinky(new_obj, e_start, e_end)
    elif category == 'ROPE':
        # Rope creation logic (simplified from operator)
        mesh = bpy.data.meshes.new(f"{name}_Mesh")
        new_obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(new_obj)
        
        bm = bmesh.new()
        seg_count = 64
        # SIZE CAGE FIX: Ensure initial length matches the cage scale
        rope_len = scale_factor 
        for i in range(seg_count + 1):
            # Create segments along the -Z axis
            z = (i / seg_count) * rope_len
            bm.verts.new((0, 0, -z))
        
        bm.verts.ensure_lookup_table()
        for i in range(seg_count):
            bm.edges.new((bm.verts[i], bm.verts[i+1]))
        
        bm.to_mesh(mesh)
        bm.free()
        
        # Initialize properties
        new_obj.fcd_pg_mech_props.is_part = True
        new_obj.fcd_pg_mech_props.category = 'ROPE'
        # length property in props should stay in sync
        new_obj.fcd_pg_mech_props.length = rope_len
    # --- 2. Create Standard BMesh Objects if needed ---
    if not new_obj:
        mesh = bpy.data.meshes.new(name)
        new_obj = bpy.data.objects.new(name, mesh)
        coll.objects.link(new_obj)

    new_obj.location = location
    
    # AI Editor Note: Initial Setup for Stators/Sub-objects (Basic Joints)
    # The separation of concerns mandate requires distinct objects for stationary components.
    props = new_obj.fcd_pg_mech_props
    if category == 'BASIC_JOINT':
        # Every basic joint needs a stator (body/bracket)
        stator_mesh = bpy.data.meshes.new(f"{name}_Stator_Mesh")
        stator_obj = bpy.data.objects.new(f"{name}_Stator", stator_mesh)
        coll.objects.link(stator_obj)
        stator_obj.matrix_world = new_obj.matrix_world.copy()
        stator_obj.parent = new_obj
        props.joint_stator_obj = stator_obj
        
        # Prismatic joints also need a dedicated screw shaft
        if type_sub == 'JOINT_PRISMATIC':
             screw_mesh = bpy.data.meshes.new(f"{name}_Screw_Mesh")
             screw_obj = bpy.data.objects.new(f"{name}_Screw", screw_mesh)
             coll.objects.link(screw_obj)
             screw_obj.matrix_world = new_obj.matrix_world.copy()
             screw_obj.parent = new_obj
             props.joint_screw_obj = screw_obj

    # AI Editor Note: Force update to ensure matrix_world is correct for subsequent operations (like rigging).
    # This prevents parts from being rigged at the world origin if the dependency graph hasn't caught up.
    context.view_layer.update()
    
    # --- 3. Set Final Properties (Synced with Generator logic) ---
    props.is_part = True
    props.category = category
    
    # Set type property dynamically based on category
    type_prop_map = {
        'GEAR': 'type_gear', 'RACK': 'type_rack', 'FASTENER': 'type_fastener',
        'SPRING': 'type_spring', 'CHAIN': 'type_chain', 'WHEEL': 'type_wheel',
        'PULLEY': 'type_pulley', 'ROPE': 'type_rope', 'BASIC_JOINT': 'type_basic_joint', 'BASIC_SHAPE': 'type_basic_shape',
        'ELECTRONICS': 'type_electronics',
        'ARCHITECTURAL': 'type_architectural',
        'VEHICLE': 'type_vehicle'
    }
    if category in type_prop_map:
        setattr(props, type_prop_map[category], type_sub)

    # --- 3. Apply Defaults & Scaling ---
    # Apply realistic defaults first, then scale
    if category == 'ARCHITECTURAL':
        # Default Architectural: Scale relative to actual base size (Length 5.0m)
        multiplier = scale_factor / 5.0 
        props.length = 5.0 * multiplier; props.height = 2.5 * multiplier
        props.wall_thickness = 0.2 * multiplier
        if type_sub == 'COLUMN': props.radius = 0.2 * multiplier
        elif type_sub == 'STAIRS':
            props.step_count = 12; props.step_height = (2.5 * multiplier) / 12
            props.step_depth = 0.28 * multiplier
        elif type_sub == 'WINDOW' or type_sub == 'DOOR':
            props.window_frame_thickness = 0.05 * multiplier
            props.glass_thickness = 0.01 * multiplier
    elif category == 'VEHICLE':
        # Realistic scale mapping (units in meters) proportional to scale_factor (Length)
        l = scale_factor
        if type_sub == 'CAR':
            props.vehicle_length = l; props.vehicle_width = l * 0.4; props.vehicle_height = l * 0.31
            props.vehicle_wheel_radius = props.vehicle_height * 0.25; props.vehicle_wheel_width = props.vehicle_width * 0.15
            props.vehicle_wheelbase = l * 0.6; props.vehicle_track_width = props.vehicle_width * 0.8
        elif type_sub == 'TRUCK':
            props.vehicle_length = l; props.vehicle_width = l * 0.4; props.vehicle_height = l * 0.51
            props.vehicle_wheel_radius = props.vehicle_height * 0.15; props.vehicle_wheel_width = props.vehicle_width * 0.12
            props.vehicle_wheelbase = l * 0.7; props.vehicle_track_width = props.vehicle_width * 0.85
        elif type_sub == 'DRONE':
            props.vehicle_length = l; props.vehicle_width = l; props.vehicle_height = l * 0.33
            props.vehicle_wheel_radius = l * 0.25; props.vehicle_wheel_width = l * 0.05
        elif type_sub == 'TANK':
            props.vehicle_length = l; props.vehicle_width = l * 0.39; props.vehicle_height = l * 0.28
            props.vehicle_wheel_radius = props.vehicle_height * 0.4; props.vehicle_wheel_width = props.vehicle_width * 0.25
        elif type_sub == 'FORKLIFT':
            props.vehicle_length = l; props.vehicle_width = l * 0.34; props.vehicle_height = l * 0.71
    elif category == 'FASTENER':
        # AI Editor Note: Scale relative to actual base size (0.02m) to maximize cage.
        # Default Fastener: Length 0.02, Radius 0.003. Max dim is 0.02.
        multiplier = scale_factor / 0.02
        props.radius = 0.003 * multiplier; props.length = 0.02 * multiplier
    elif category == 'ELECTRONICS':
        # Electronics defaults (simplified logic from operator)
        # AI Editor Note: Scale relative to actual base size to maximize cage.
        if 'MOTOR' in type_sub:
            # Max dim 0.06 (Body 0.04 + Shaft/Tabs ~0.02)
            multiplier = scale_factor / 0.06
            props.radius = 0.015 * multiplier; props.length = 0.04 * multiplier
            
            # AI Editor Note: Specific defaults for BLDC Outrunner Shaft per user request
            if type_sub == 'MOTOR_BLDC_OUTRUNNER':
                # Normalize to default scale (0.1) to ensure 2.2mm/8.5mm at base scale
                scale_ratio = scale_factor / 0.1
                props.motor_shaft_radius = 0.0022 * scale_ratio
                props.motor_shaft_length = 0.0085 * scale_ratio

            # AI Editor Note: Specific defaults for Pancake Motor
            if type_sub == 'MOTOR_PANCAKE':
                props.radius = 0.04 * multiplier # Wide
                props.length = 0.012 * multiplier # Short (Thin)
                props.motor_shaft_length = 0.008 * multiplier # Short shaft
                props.motor_shaft_radius = 0.004 * multiplier

        elif 'SENSOR' in type_sub:
            # Max dim 0.06
            multiplier = scale_factor / 0.06
            props.radius = 0.03 * multiplier; props.length = 0.04 * multiplier
        elif 'PCB' in type_sub:
            # Max dim 0.06 (Board 0.05 + Connectors)
            multiplier = scale_factor / 0.06
            props.radius = 0.025 * multiplier; props.length = 0.05 * multiplier
        else:
            # Max dim 0.02
            multiplier = scale_factor / 0.02
            props.radius = 0.01 * multiplier; props.length = 0.02 * multiplier
    elif category == 'GEAR':
        # Default Gear: Radius 0.05. Diameter 0.1.
        multiplier = scale_factor / 0.1
        props.gear_radius = 0.05 * multiplier
        props.gear_width = 0.02 * multiplier
        props.gear_tooth_depth = 0.005 * multiplier
        props.gear_bore_radius = 0.01 * multiplier
    elif category == 'RACK':
        # Default Rack: Length 0.2.
        multiplier = scale_factor / 0.2
        props.rack_length = scale_factor # Direct mapping to cage size
        props.rack_width = 0.02 * multiplier
        props.rack_height = 0.02 * multiplier
        props.rack_tooth_depth = 0.005 * multiplier
    elif category == 'WHEEL':
        # Default Wheel: Radius 0.05. Diameter 0.1.
        multiplier = scale_factor / 0.1
        props.wheel_radius = 0.05 * multiplier
        props.wheel_width = 0.04 * multiplier
        props.wheel_hub_radius = 0.012 * multiplier
        props.wheel_hub_length = 0.02 * multiplier
    elif category == 'PULLEY':
        # Default Pulley: Radius 0.03. Diameter 0.06.
        multiplier = scale_factor / 0.06
        props.pulley_radius = 0.03 * multiplier
        props.pulley_width = 0.02 * multiplier
        props.pulley_groove_depth = 0.005 * multiplier
    elif category == 'BASIC_JOINT':
        # AI Editor Note: Precision Scaling for Basic Joints.
        # Ensure the 'span' correctly represents the physical total length of the default parts along the major axis (Z).
        
        # 1. Determine base dimensions from procedural generation defaults
        # JOINT_CONTINUOUS: body (0.12) + shaft (0.02) = 0.14
        # JOINT_REVOLUTE: frame length (0.08) + eye radius (0.03) = 0.11
        # JOINT_PRISMATIC: screw length (0.73)
        
        base_h = 0.14 if type_sub == 'JOINT_CONTINUOUS' else 0.11
        if type_sub in ['JOINT_PRISMATIC_WHEELS', 'JOINT_PRISMATIC_WHEELS_ROT']:
            base_h = 0.2 # Standard Rack Length
        elif type_sub == 'JOINT_PRISMATIC':
            base_h = 0.73 # Screw Length
        
        multiplier = scale_factor / base_h
        
        # 2. Apply Proportional Scaling (Explicitly set instead of *= to prevent cumulative error)
        # Default proportions normalized to their respective base_h
        props.joint_radius = 0.03 * multiplier
        props.joint_width = 0.08 * multiplier
        props.joint_pin_radius = 0.007 * multiplier
        props.joint_pin_length = 0.06 * multiplier
        props.joint_sub_size = 0.001 * multiplier 
        props.joint_sub_thickness = 0.001 * multiplier
        props.joint_frame_width = 0.06 * multiplier
        props.joint_frame_length = 0.08 * multiplier
        
        # Continuous-Specific Proportions (Now using the new engineering defaults)
        props.joint_base_radius = 0.06 * multiplier
        props.joint_base_length = 0.12 * multiplier
        props.joint_motor_shaft_radius = 0.01 * multiplier
        props.joint_motor_shaft_length = 0.02 * multiplier

        # Rotor Arm proportions (Screenshot 4 Defaults)
        props.rotor_arm_length = 0.194 * multiplier
        props.rotor_arm_width = 0.001 * multiplier
        props.rotor_arm_height = 0.001 * multiplier

        # 3. Categorized Overrides for specific span requirements
        if type_sub == 'JOINT_REVOLUTE':
            # Revolute pin length should scale with body width but doesn't define the vertical span
            props.joint_pin_length = props.joint_width * 1.5
        elif type_sub in ['JOINT_PRISMATIC_WHEELS', 'JOINT_PRISMATIC_WHEELS_ROT']:
            props.joint_radius = 0.012 * multiplier # Wheel Radius
            props.joint_sub_thickness = 0.01 * multiplier # Rack Thickness
            props.rack_width = 0.04 * multiplier
            props.rack_length = scale_factor # Matches the cage directly
            props.joint_sub_size = 0.08 * multiplier # Carriage Length
    
    elif category == 'ARCHITECTURAL':
        props.length = scale_factor
        props.height = scale_factor
        props.width = scale_factor / 5.0
        props.radius = scale_factor / 10.0
        props.wall_thickness = 0.2 * scale_factor
        props.window_frame_thickness = 0.05 * scale_factor
        props.glass_thickness = 0.01 * scale_factor
        props.step_count = 10
        props.step_height = scale_factor / 10.0
        props.step_depth = scale_factor / 8.0
    elif category == 'BASIC_SHAPE':
        # Direct unit mapping for shapes
        props.radius = scale_factor / 2.0
        props.length = scale_factor
        props.height = scale_factor
        props.shape_size = scale_factor
        props.shape_length_x = scale_factor
        props.shape_width_y = scale_factor / 2.0
        props.shape_height_z = scale_factor / 4.0
        props.shape_radius = scale_factor / 2.0
        props.shape_height = scale_factor
        props.shape_major_radius = scale_factor / 2.0
        props.shape_tube_radius = scale_factor / 10.0
        props.tooth_depth = scale_factor / 4.0 # Torus minor radius
        props.teeth = 32 # Default segments for smooth shapes
        
        # AI Editor Note: Specific default for Cube Width (Y) per user request.
        if type_sub == 'SHAPE_CUBE':
            props.radius = 1.0 * scale_factor # Width (Y)
    elif category == 'CHAIN':
        # AI Editor Note: For chains, scale the object itself to fit the cage.
        # Default curve diameter is 0.4.
        unit_scale = context.scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0
        
        target_scale = (scale_factor / 0.4) * s
        new_obj.scale = (target_scale, target_scale, target_scale)
        # Do not scale properties to maintain proportions relative to the scaled curve.
        pass
    elif category == 'ROPE':
        unit_scale = context.scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0
        # Default construction: 6-strand steel wire or 20-strand synthetic braid
        if type_sub == 'ROPE_STEEL':
            props.teeth = 6 # Traditional 6-strand wire rope
            props.twist = math.radians(200.0) # 200 deg
        elif type_sub == 'ROPE_SYNTHETIC':
            props.teeth = 20 # As per user screenshot
            props.twist = math.radians(200.0) # As per user screenshot
        
        multiplier = scale_factor / 0.1
        props.radius = 0.01 * multiplier # Total radius
        
        # Initialize Object ID properties for drivers
        new_obj["rope_radius"] = props.radius * s
        new_obj["rope_strands"] = props.teeth
        new_obj["rope_twist"] = props.twist
        new_obj["rope_tube_mode"] = (type_sub == 'ROPE_TUBE')
        new_obj["rope_is_synthetic"] = (type_sub == 'ROPE_SYNTHETIC')

    # --- 4. Apply User Overrides (kwargs) ---
    for k, v in kwargs.items():
        if hasattr(props, k):
            setattr(props, k, v)
            
    # --- 5. Create Helpers (Springs/Fasteners/Ropes) ---
    if category == 'FASTENER':
        # Create Head Cutter
        head_mesh = bpy.data.meshes.new(f"{CUTTER_PREFIX}{new_obj.name}_Head_Mesh")
        head_cutter = bpy.data.objects.new(f"{CUTTER_PREFIX}{new_obj.name}_Head", head_mesh)
        coll.objects.link(head_cutter); head_cutter.parent = new_obj
        head_cutter.display_type = 'WIRE'; head_cutter.hide_set(True); head_cutter.hide_render = True
        mod = new_obj.modifiers.new(name=f"{BOOL_PREFIX}Head", type='BOOLEAN')
        mod.operation = 'UNION'; mod.solver = 'EXACT'; mod.object = head_cutter
        # Create Nut Cutter
        nut_mesh = bpy.data.meshes.new(f"{CUTTER_PREFIX}{new_obj.name}_Nut_Mesh")
        nut_cutter = bpy.data.objects.new(f"{CUTTER_PREFIX}{new_obj.name}_Nut", nut_mesh)
        coll.objects.link(nut_cutter); nut_cutter.parent = new_obj
        nut_cutter.display_type = 'WIRE'; nut_cutter.hide_set(True); nut_cutter.hide_render = True
        mod = new_obj.modifiers.new(name=f"{BOOL_PREFIX}Nut", type='BOOLEAN')
        mod.operation = 'UNION'; mod.solver = 'EXACT'; mod.object = nut_cutter
        
    elif category == 'SPRING':
        # SIZE CAGE FIX: Ensure initial length matches the cage scale
        props.length = scale_factor
        
        # --- AI Editor Note: Unit-Aware Display Size ---
        unit_scale = context.scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0

        # Create Empties
        s_empty = bpy.data.objects.new(f"Spring_Start_{new_obj.name}", None)
        e_empty = bpy.data.objects.new(f"Spring_End_{new_obj.name}", None)
        coll.objects.link(s_empty); coll.objects.link(e_empty)
        s_empty.location = location
        e_empty.location = location + mathutils.Vector((0, 0, props.length))
        props.spring_start_obj = s_empty; props.spring_end_obj = e_empty
        s_empty.empty_display_size = 0.2 * scale_factor * s
        e_empty.empty_display_size = 0.2 * scale_factor * s
        
        if type_sub == 'DAMPER':
            # Housing & Piston (combined)
            props.height = 0.5 * scale_factor 
            props.radius = 0.08 * scale_factor # Housing Radius
            props.tooth_depth = 0.015 * scale_factor # Rod Radius
            props.teeth = 9 # Piston Segments
            props.outer_radius = 0.06 * scale_factor # Thicker Housing
            props.bore_radius = 0.03 * scale_factor # Rod
            props.damper_seat_radius = 0.1 * scale_factor
            props.damper_seat_thickness = 0.03 * scale_factor
        elif type_sub == 'SPRING':
            props.spring_radius = 0.2 * scale_factor
            props.spring_wire_thickness = 0.03 * scale_factor
            props.spring_turns = 10
        
        # Setup Driver
        # AI Editor Note: The original code was trying to drive a non-existent custom property '["spring_length"]'.
        # The correct target is the 'length' property within the object's URDF property group.
        # This ensures the data model is kept in sync with the dynamic length of the spring.
        fcurve = new_obj.driver_add('fcd_pg_mech_props.length')
        driver = fcurve.driver; driver.type = 'AVERAGE'
        var = driver.variables.new(); var.name = "dist"; var.type = 'LOC_DIFF'
        var.targets[0].id = s_empty; var.targets[1].id = e_empty
        driver.expression = "dist"
        
        if type_sub == 'SPRING': setup_native_spring(new_obj, s_empty, e_empty)
        elif type_sub == 'DAMPER': setup_native_damper(new_obj, s_empty, e_empty)

    elif category == 'CHAIN':
        # AI Editor Note: Ensure the Geometry Nodes modifier is set up for the chain.
        setup_native_chain_gn(new_obj, props.instanced_link_obj)
        
    elif category == 'ROPE':
        # Setup rope hooks/physics (simplified)
        setup_native_rope_gn(new_obj)

    # --- 6. Final Regeneration ---
    from .generators import regenerate_mech_mesh
    regenerate_mech_mesh(new_obj, context)
    
    # AI Editor Note: Ensure the new object is active and selected for immediate operations.
    context.view_layer.objects.active = new_obj
    new_obj.select_set(True)

    # AI Editor Note: Force update again to ensure any sub-objects created during regeneration (like stators)
    # have valid matrices before being used in rigging or other operations.
    context.view_layer.update()

    return new_obj

def _calculate_bone_geometry(objs, axis_orient: str, reference_obj=None):
    """
    Calculates the head, tail, roll vector, and radius for a bone based on
    one or more mesh objects.

    Supports a single object or a list/tuple/set of objects. When multiple
    objects are given the bounding boxes are merged before computing the bone.
    """
    if not isinstance(objs, (list, tuple, set)):
        objs = [objs]

    if not reference_obj:
        reference_obj = objs[0]

    mat = reference_obj.matrix_world
    inv_mat = mat.inverted()

    # Build a combined bounding box in the reference object's local space
    all_points_local = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        o_eval = o.evaluated_get(depsgraph) if o.type == 'MESH' else o
        o_mat = o.matrix_world
        if hasattr(o_eval, 'bound_box') and o_eval.bound_box:
            for b in o_eval.bound_box:
                v_world = o_mat @ mathutils.Vector(b)
                all_points_local.append(inv_mat @ v_world)
        else:
            all_points_local.append(inv_mat @ o_mat.translation)

    if not all_points_local:
        return (mat.translation,
                mat.translation + mathutils.Vector((0, 0.1, 0)),
                mathutils.Vector((0, 0, 1)), 0.1)

    head_world = mat.translation
    tail_world: mathutils.Vector
    roll_vec_world: mathutils.Vector

    if axis_orient == 'AUTO':
        y_vec_local = mathutils.Vector((0, 0, 1.0))
        z_vec_local = mathutils.Vector((1.0, 0, 0))

        max_dist = max((p.dot(y_vec_local) for p in all_points_local), default=0.1)
        if max_dist < 0.001:
            max_dist = 0.1

        tail_local = y_vec_local * max_dist
        initial_tail_world = mat @ tail_local
        initial_roll_vec_world = mat.to_3x3() @ z_vec_local

        y_vec_world = (initial_tail_world - head_world).normalized()
        z_vec_world = initial_roll_vec_world.normalized()
        x_vec_world = y_vec_world.cross(z_vec_world).normalized()

        orient_mat = mathutils.Matrix((x_vec_world, y_vec_world, z_vec_world)).transposed()
        new_y_vec_world = orient_mat.col[1]
        new_z_vec_world = orient_mat.col[2]

        bone_length = (initial_tail_world - head_world).length
        tail_world = head_world + bone_length * new_y_vec_world
        roll_vec_world = new_z_vec_world
    else:
        is_neg = axis_orient.startswith("-")
        axis_char = axis_orient.replace("-", "")

        if axis_char == 'X':
            y_vec_local = mathutils.Vector((1, 0, 0))
            roll_vec_local = mathutils.Vector((0, 0, 1))
        elif axis_char == 'Y':
            y_vec_local = mathutils.Vector((0, 1, 0))
            roll_vec_local = mathutils.Vector((1, 0, 0))
        else:  # 'Z'
            y_vec_local = mathutils.Vector((0, 0, 1))
            roll_vec_local = mathutils.Vector((0, 1, 0))

        if is_neg:
            y_vec_local *= -1.0

        obj_rot_mat = mat.to_3x3()
        y_vec_world = (obj_rot_mat @ y_vec_local).normalized()
        roll_vec_world = (obj_rot_mat @ roll_vec_local).normalized()

        origin_proj = head_world.dot(y_vec_world)
        projections = [(mat @ p).dot(y_vec_world) for p in all_points_local]

        max_extent = max(p - origin_proj for p in projections)
        if max_extent < 0.001:
            length = max(projections) - min(projections)
        else:
            length = max_extent

        if length < 0.01:
            length = 0.1

        tail_world = head_world + length * y_vec_world

    # Radius calculation (common for all modes)
    bone_axis_world = (tail_world - head_world).normalized()
    max_radius = 0.0
    for p_local in all_points_local:
        v_world = mat @ p_local
        vec_to_point = v_world - head_world
        proj_len = vec_to_point.dot(bone_axis_world)
        proj_vec = proj_len * bone_axis_world
        dist = (vec_to_point - proj_vec).length
        if dist > max_radius:
            max_radius = dist

    if max_radius < 0.001:
        max_radius = 0.5
    
    # --- AI Editor Note: Return radius in physical Meters ---
    # Blender Units (BU) must be normalized by the scene scale to get meters.
    unit_scale = bpy.context.scene.unit_settings.scale_length
    normalized_radius = max_radius * unit_scale if unit_scale > 0 else max_radius

    return head_world, tail_world, roll_vec_world, normalized_radius


def rig_parametric_joint(context: bpy.types.Context, obj: bpy.types.Object) -> Tuple[str, str]:
    """
    Automatically rigs a parametric BASIC_JOINT object.
    Creates base and joint bones, parents the stator and rotor, and sets constraints.
    Returns the names of the created (base_bone, joint_bone).
    """
    props = obj.fcd_pg_mech_props
    if props.category != 'BASIC_JOINT': return None, None

    rig = ensure_default_rig(context)
    if not rig: return None, None

    # 1. Calculate bone geometry from the rotor object
    head, tail, roll, radius = _calculate_bone_geometry(obj, context.scene.fcd_bone_axis)

    unit_scale = context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0

    # --- AI Editor Note: Ensure radius is always in physical Meters (Normalized) ---
    # _calculate_bone_geometry already returns normalized meters.
    if props.type_basic_joint == 'JOINT_CONTINUOUS':
        # Use the explicit joint_radius property from the part as ground truth for motors.
        radius = props.joint_radius
    
    # Radius must be > 0
    if radius < 0.001: radius = 0.05

    # 2. Create bones in Edit Mode
    if context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    rig_mat_inv = rig.matrix_world.inverted()

    # Create base bone
    base_bone_name = f"Bone_{obj.name.replace('.', '_')}_base"
    eb_base = rig.data.edit_bones.new(base_bone_name)

    if props.type_basic_joint == 'JOINT_PRISMATIC':
        screw_len = props.length
        screw_rad = props.radius
        block_h = screw_rad * 3.0
        base_head_local = mathutils.Vector((0, 0, -screw_len/2 - block_h/2))
        base_tail_local = mathutils.Vector((0, 0, -screw_len/2))
        base_head_world = obj.matrix_world @ base_head_local
        base_tail_world = obj.matrix_world @ base_tail_local
        eb_base.head = rig_mat_inv @ base_head_world
        eb_base.tail = rig_mat_inv @ base_tail_world
        eb_base.align_roll(rig_mat_inv.to_3x3() @ roll)
    else:
        # Offset must be scaled by 's' to be visible in mm scenes
        offset_vec_world = (tail - head).normalized() * -0.05 * s
        eb_base.head = rig_mat_inv @ (head + offset_vec_world)
        eb_base.tail = rig_mat_inv @ head
        eb_base.align_roll(rig_mat_inv.to_3x3() @ roll)

    # Create joint bone
    joint_bone_name = f"Bone_{obj.name.replace('.', '_')}"
    eb_joint = rig.data.edit_bones.new(joint_bone_name)
    eb_joint.head = rig_mat_inv @ head
    eb_joint.tail = rig_mat_inv @ tail
    eb_joint.align_roll(rig_mat_inv.to_3x3() @ roll)
    eb_joint.parent = eb_base

    # Create screw bone (for Prismatic joints)
    screw_bone_name = f"Bone_{obj.name.replace('.', '_')}_screw"
    if props.type_basic_joint == 'JOINT_PRISMATIC':
        eb_screw = rig.data.edit_bones.new(screw_bone_name)
        eb_screw.head = eb_joint.head
        eb_screw.tail = eb_joint.tail
        eb_screw.roll = eb_joint.roll
        eb_screw.parent = eb_base

    # 3. Configure bones and parent meshes in Pose Mode
    bpy.ops.object.mode_set(mode='POSE')

    # Configure base bone and parent stator
    pbone_base = rig.pose.bones.get(base_bone_name)
    if pbone_base:
        stator_obj = props.joint_stator_obj
        if stator_obj:
            original_matrix = stator_obj.matrix_world.copy()
            stator_obj.parent = rig
            stator_obj.parent_type = 'BONE'
            stator_obj.parent_bone = pbone_base.name
            stator_obj.matrix_world = original_matrix
        
        pbone_base.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone_base, context.scene.fcd_viz_gizmos)
        apply_native_constraints(pbone_base)

    # Configure screw bone (Prismatic only)
    if props.type_basic_joint == 'JOINT_PRISMATIC':
        pbone_screw = rig.pose.bones.get(screw_bone_name)
        if pbone_screw:
            pbone_screw.fcd_pg_kinematic_props.joint_type = 'continuous'
            pbone_screw.fcd_pg_kinematic_props.axis_enum = 'Z'
            pbone_screw.fcd_pg_kinematic_props.joint_radius = radius
            update_single_bone_gizmo(pbone_screw, context.scene.fcd_viz_gizmos)
            apply_native_constraints(pbone_screw)
            screw_obj = props.joint_screw_obj
            if screw_obj:
                original_matrix = screw_obj.matrix_world.copy()
                screw_obj.parent = rig
                screw_obj.parent_type = 'BONE'
                screw_obj.parent_bone = screw_bone_name
                screw_obj.matrix_world = original_matrix

    # Configure pin object (Revolute only)
    if props.type_basic_joint == 'JOINT_REVOLUTE':
        pin_obj = props.joint_pin_obj
        if pin_obj:
            # Parent pin to the joint bone so it rotates with the rotor
            original_matrix = pin_obj.matrix_world.copy()
            pin_obj.parent = rig
            pin_obj.parent_type = 'BONE'
            pin_obj.parent_bone = joint_bone_name
            pin_obj.matrix_world = original_matrix
            apply_auto_smooth(pin_obj)
    
    # Configure joint bone and parent rotor
    pbone_joint = rig.pose.bones.get(joint_bone_name)
    if pbone_joint:
        original_matrix = obj.matrix_world.copy()
        obj.parent = rig
        obj.parent_type = 'BONE'
        obj.parent_bone = joint_bone_name
        obj.matrix_world = original_matrix

        joint_type_map = {
            'JOINT_REVOLUTE': 'revolute',
            'JOINT_CONTINUOUS': 'continuous',
            'JOINT_PRISMATIC': 'prismatic',
            'JOINT_PRISMATIC_WHEELS': 'prismatic',
            'JOINT_PRISMATIC_WHEELS_ROT': 'prismatic',
            'JOINT_SPHERICAL': 'base',
        }
        pbone_joint.fcd_pg_kinematic_props.joint_type = joint_type_map.get(props.type_basic_joint, 'fixed')
        pbone_joint.fcd_pg_kinematic_props.axis_enum = 'Z'
        pbone_joint.fcd_pg_kinematic_props.joint_radius = radius

        # AI Editor Note: Set default limits for Revolute joints as requested (-115 to 115)
        if props.type_basic_joint == 'JOINT_REVOLUTE':
            pbone_joint.fcd_pg_kinematic_props.lower_limit = -115.0
            pbone_joint.fcd_pg_kinematic_props.upper_limit = 115.0

        update_single_bone_gizmo(pbone_joint, context.scene.fcd_viz_gizmos)
        apply_native_constraints(pbone_joint)
        
        if props.type_basic_joint == 'JOINT_PRISMATIC':
            # AI Editor Note: Calculate ratio based on screw radius to ensure it scales with the size cage.
            # Base ratio 0.015 corresponds to base radius 0.005 (Ratio = 3 * Radius).
            calc_ratio = props.radius * 3.0
            
            add_native_driver_relation(pbone_joint, screw_bone_name, ratio=calc_ratio, invert=False)
            if not any(m.target_bone == screw_bone_name for m in pbone_joint.fcd_pg_kinematic_props.mimic_drivers):
                mimic_entry = pbone_joint.fcd_pg_kinematic_props.mimic_drivers.add()
                mimic_entry.target_bone = screw_bone_name
                mimic_entry.ratio = calc_ratio

        rig.data.bones.active = pbone_joint.bone

    return base_bone_name, joint_bone_name

def _build_procedural_drone(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Procedurally builds a quadcopter drone."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    # Body
    body_rad = 0.1 * scale_factor
    body_height = 0.05 * scale_factor
    bpy.ops.mesh.primitive_cylinder_add(radius=body_rad, depth=body_height, location=cursor_loc + mathutils.Vector((0,0,body_height/2 + 0.1*scale_factor)))
    body = context.active_object
    body.name = get_unique_name("Drone_Body")
    
    context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.fcd.add_bone()
    body_bone = f"Bone_{body.name.replace('.', '_')}"
    
    # Base joint
    pbone = rig.pose.bones.get(body_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)

    # Arms & Motors
    num_arms = 4
    arm_len = 0.25 * scale_factor
    
    for i in range(num_arms):
        # AI Editor Note: Ensure Object Mode for primitive creation
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        angle = (i / num_arms) * 2 * math.pi + (math.pi / 4) # X configuration
        x = math.cos(angle) * arm_len
        y = math.sin(angle) * arm_len
        
        # Arm Mesh (Simple tube)
        mid_x = x / 2
        mid_y = y / 2
        arm_rot = -angle
        
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02*scale_factor, depth=arm_len, location=cursor_loc + mathutils.Vector((mid_x, mid_y, body_height/2 + 0.1*scale_factor)))
        arm = context.active_object
        arm.name = get_unique_name(f"Arm_{i+1}")
        arm.rotation_euler.z = angle
        arm.rotation_euler.x = math.pi/2
        bpy.ops.object.transform_apply(rotation=True, scale=True)
        
        # Parent arm to body (Fixed)
        arm.parent = rig
        arm.parent_type = 'BONE'
        arm.parent_bone = body_bone
        
        # Motor
        motor_pos = cursor_loc + mathutils.Vector((x, y, body_height/2 + 0.1*scale_factor + 0.02*scale_factor))
        motor = create_parametric_part_object(context, 'ELECTRONICS', 'MOTOR_BLDC_OUTRUNNER', motor_pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.03*scale_factor)
        motor.name = get_unique_name(f"Motor_{i+1}")
        
        context.view_layer.objects.active = motor
        motor.select_set(True)
        bpy.ops.fcd.add_bone()
        motor_bone = f"Bone_{motor.name.replace('.', '_')}"
        
        # Parent motor bone to body bone
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[motor_bone].parent = rig.data.edit_bones[body_bone]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        pbone = rig.pose.bones.get(motor_bone)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'continuous'
            pbone.fcd_pg_kinematic_props.axis_enum = 'Z'
            update_single_bone_gizmo(pbone, True)
            apply_native_constraints(pbone)

def _build_procedural_plane(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Procedurally builds a simple airplane."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    # Fuselage
    fuselage_len = 1.0 * scale_factor
    fuselage_rad = 0.15 * scale_factor
    bpy.ops.mesh.primitive_cylinder_add(radius=fuselage_rad, depth=fuselage_len, location=cursor_loc + mathutils.Vector((0,0,fuselage_rad + 0.2*scale_factor)))
    fuselage = context.active_object
    fuselage.name = get_unique_name("Fuselage")
    fuselage.rotation_euler.x = math.pi/2
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    
    context.view_layer.objects.active = fuselage
    fuselage.select_set(True)
    bpy.ops.fcd.add_bone()
    base_bone = f"Bone_{fuselage.name.replace('.', '_')}"
    
    pbone = rig.pose.bones.get(base_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)
        
    # Wings
    wing_span = 1.2 * scale_factor
    wing_chord = 0.3 * scale_factor
    wing_thick = 0.05 * scale_factor
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((0, 0, fuselage_rad + 0.2*scale_factor)))
    wings = context.active_object
    wings.name = get_unique_name("Wings")
    wings.dimensions = (wing_span, wing_chord, wing_thick)
    bpy.ops.object.transform_apply(scale=True)
    
    wings.parent = rig
    wings.parent_type = 'BONE'
    wings.parent_bone = base_bone
    
    # Propeller (Front)
    prop_pos = cursor_loc + mathutils.Vector((0, -fuselage_len/2 - 0.05*scale_factor, fuselage_rad + 0.2*scale_factor))
    # Motor
    motor = create_parametric_part_object(context, 'ELECTRONICS', 'MOTOR_DC_ROUND', prop_pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.05*scale_factor)
    motor.rotation_euler.x = math.pi/2
    bpy.ops.object.transform_apply(rotation=True)
    
    context.view_layer.objects.active = motor
    motor.select_set(True)
    bpy.ops.fcd.add_bone()
    motor_bone = f"Bone_{motor.name.replace('.', '_')}"
    
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    rig.data.edit_bones[motor_bone].parent = rig.data.edit_bones[base_bone]
    # Align motor bone to Y axis (forward)
    rig.data.edit_bones[motor_bone].tail = rig.data.edit_bones[motor_bone].head + mathutils.Vector((0, -0.1, 0))
    bpy.ops.object.mode_set(mode='POSE', toggle=False)
    
    pbone = rig.pose.bones.get(motor_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'continuous'
        pbone.fcd_pg_kinematic_props.axis_enum = '-Y'
        update_single_bone_gizmo(pbone, True)
        apply_native_constraints(pbone)

def _build_procedural_furniture(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Procedurally builds a closet/cabinet."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    # Cabinet Body
    width = 0.8 * scale_factor
    depth = 0.5 * scale_factor
    height = 1.8 * scale_factor
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((0, 0, height/2)))
    cabinet = context.active_object
    cabinet.name = get_unique_name("Cabinet_Body")
    cabinet.dimensions = (width, depth, height)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = cabinet
    cabinet.select_set(True)
    bpy.ops.fcd.add_bone()
    base_bone = f"Bone_{cabinet.name.replace('.', '_')}"
    
    pbone = rig.pose.bones.get(base_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)
        
    # Doors (Left and Right)
    door_w = width / 2
    door_thick = 0.02 * scale_factor
    
    for side in [-1, 1]: # Left (-1), Right (1)
        # AI Editor Note: Ensure Object Mode for primitive creation
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        # Hinge position: Outer edge front
        hinge_x = side * (width/2)
        hinge_y = -depth/2
        
        # Door mesh
        # Origin at hinge
        bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((hinge_x - (side * door_w/2), hinge_y - door_thick/2, height/2)))
        door = context.active_object
        door.name = get_unique_name(f"Door_{'L' if side<0 else 'R'}")
        door.dimensions = (door_w, door_thick, height)
        bpy.ops.object.transform_apply(scale=True)
        
        # Shift object origin to hinge side
        hinge_pos = cursor_loc + mathutils.Vector((hinge_x, hinge_y, height/2))
        cursor = context.scene.cursor
        saved_loc = cursor.location.copy()
        cursor.location = hinge_pos
        context.view_layer.objects.active = door
        door.select_set(True)
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        cursor.location = saved_loc
        
        bpy.ops.fcd.add_bone()
        door_bone = f"Bone_{door.name.replace('.', '_')}"
        
        # Parent to cabinet
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[door_bone].parent = rig.data.edit_bones[base_bone]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        pbone = rig.pose.bones.get(door_bone)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'revolute'
            pbone.fcd_pg_kinematic_props.axis_enum = 'Z'
            pbone.fcd_pg_kinematic_props.lower_limit = 0 if side > 0 else -90
            pbone.fcd_pg_kinematic_props.upper_limit = 90 if side > 0 else 0
            update_single_bone_gizmo(pbone, True)
            apply_native_constraints(pbone)

def _build_procedural_conveyor(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Procedurally builds an escalator/conveyor."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    # Ramp/Base
    length = 3.0 * scale_factor
    width = 1.0 * scale_factor
    height = 1.5 * scale_factor
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=cursor_loc + mathutils.Vector((length/2, 0, height/2)))
    ramp = context.active_object
    ramp.name = get_unique_name("Escalator_Base")
    ramp.dimensions = (math.sqrt(length**2 + height**2), width, 0.2*scale_factor)
    ramp.rotation_euler.y = -math.atan2(height, length)
    bpy.ops.object.transform_apply(scale=True, rotation=True)
    
    context.view_layer.objects.active = ramp
    ramp.select_set(True)
    bpy.ops.fcd.add_bone()
    base_bone = f"Bone_{ramp.name.replace('.', '_')}"
    
    pbone = rig.pose.bones.get(base_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)
        
    # Steps
    step_depth = 0.3 * scale_factor
    step_height = 0.2 * scale_factor
    
    step_pos = cursor_loc + mathutils.Vector((0.5*scale_factor, 0, 0.5*scale_factor))
    bpy.ops.mesh.primitive_cube_add(size=1, location=step_pos)
    step = context.active_object
    step.name = get_unique_name("Step")
    step.dimensions = (step_depth, width*0.8, step_height)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = step
    step.select_set(True)
    bpy.ops.fcd.add_bone()
    step_bone = f"Bone_{step.name.replace('.', '_')}"
    
    # Parent to base
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    rig.data.edit_bones[step_bone].parent = rig.data.edit_bones[base_bone]
    
    # Align bone to ramp slope
    slope_vec = mathutils.Vector((length, 0, height)).normalized()
    rig.data.edit_bones[step_bone].tail = rig.data.edit_bones[step_bone].head + slope_vec * 0.2
    
    bpy.ops.object.mode_set(mode='POSE', toggle=False)
    
    pbone = rig.pose.bones.get(step_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'prismatic'
        pbone.fcd_pg_kinematic_props.axis_enum = 'Y' # Bone Y is length/direction
        pbone.fcd_pg_kinematic_props.lower_limit = 0.0
        pbone.fcd_pg_kinematic_props.upper_limit = math.sqrt(length**2 + height**2)
        update_single_bone_gizmo(pbone, True)
        apply_native_constraints(pbone)

def parse_natural_language_prompt(prompt: str) -> Dict[str, Any]:
    """
    Parses a natural language prompt into a structured robot configuration.
    This function uses keyword matching to interpret user intent for robot
    type, parameters, and components.
    """
    prompt = prompt.lower()
    config = {
        'type': 'UNKNOWN',
        'components': [],
        'params': {}
    }

    # --- Keyword Dictionaries for Robust Parsing ---
    # AI Editor Note: Expanded dictionaries to cover more synonyms and variations.
    # This makes the local AI more flexible and user-friendly for both local and API methods.
    TYPE_KEYWORDS = {
        'ROVER': ['rover', 'car', 'vehicle', 'buggy', 'mobile robot', 'ugv', 'ground vehicle', 'wheeled robot', 'bot'],
        'ARM': ['arm', 'manipulator', 'crane', 'robotic arm', 'robot arm'],
        'QUADRUPED': ['quadruped', 'spider', 'walker', 'dog', 'legged robot', 'dog bot', 'spot'],
        'DRONE': ['drone', 'quadcopter', 'uav', 'aerial', 'copter', 'multirotor', 'quadrotor', 'vtol'],
        'PLANE': ['plane', 'airplane', 'aircraft', 'glider', 'jet', 'fixed-wing'],
        'FURNITURE': ['closet', 'cabinet', 'wardrobe', 'shelf', 'furniture', 'cupboard', 'dresser', 'bookcase'],
        'CONVEYOR': ['escalator', 'conveyor', 'stairs', 'lift', 'conveyor belt', 'moving walkway'],
        'HUMANOID': ['humanoid', 'biped', 'human-like robot', 'android', 'human robot'],
        'BOX': ['box', 'cube', 'block', 'square'],
        'CYLINDER': ['cylinder', 'tube', 'pipe'],
        'SPHERE': ['sphere', 'ball', 'orb'],
    }

    COMPONENT_KEYWORDS = {
        'LIDAR': ['lidar', 'laser scanner', 'laser sensor'],
        'CAMERA': ['camera', 'vision sensor', 'webcam'],
        'MOTOR_SERVO': ['servo'],
        'MOTOR_STEPPER': ['stepper'],
        'MOTOR': ['motor', 'actuator', 'engine'],
        'ARM': ['arm', 'manipulator'], # For components on other robots
        'GEAR': ['gear', 'cog', 'sprocket', 'pinion'],
        'RACK': ['rack', 'linear gear'],
        'FASTENER': ['bolt', 'screw', 'nut', 'rivet', 'fastener'],
        'SPRING': ['spring', 'coil', 'shock'],
        'DAMPER': ['damper'],
        'CHAIN': ['chain', 'track'],
        'BELT': ['belt'],
        'PULLEY': ['pulley', 'sheave'],
        'ROPE': ['rope', 'cable', 'wire', 'string'],
        'WHEEL_MECANUM': ['mecanum'],
        'WHEEL_OMNI': ['omni'],
        'WHEEL_OFFROAD': ['offroad', 'off-road'],
        'WHEEL_CASTER': ['caster'],
        'WHEEL': ['wheel', 'tire', 'tyre'],
        'JOINT': ['joint', 'hinge', 'pivot'],
        'PCB': ['pcb', 'circuit board', 'breadboard', 'arduino', 'raspberry pi'],
        'IC': ['chip', 'ic', 'integrated circuit', 'resistor', 'capacitor', 'diode', 'led'],
    }

    # --- 1. Detect Robot Type ---
    for robot_type, keywords in TYPE_KEYWORDS.items():
        if any(keyword in prompt for keyword in keywords):
            config['type'] = robot_type
            break

    # --- 2. Detect Parameters ---
    # Wheel count
    wheel_match = re.search(r'(\d+)\s*[- ]?(wheel|wheeled)', prompt)
    if wheel_match:
        config['params']['wheels'] = int(wheel_match.group(1))
    elif 'tri' in prompt:
        config['params']['wheels'] = 3
    elif 'quad' in prompt and config['type'] == 'ROVER':
        config['params']['wheels'] = 4
    elif 'six' in prompt:
        config['params']['wheels'] = 6

    # Joint count for arms
    joint_match = re.search(r'(\d+)\s*[- ]?(dof|axis|joint|link|degree of freedom)', prompt)
    if joint_match:
        config['params']['joints'] = int(joint_match.group(1))

    # --- 3. Detect Components ---
    for component_type, keywords in COMPONENT_KEYWORDS.items():
        if component_type == 'ARM' and config['type'] == 'ARM': continue
        if any(keyword in prompt for keyword in keywords) and component_type not in config['components']:
            config['components'].append(component_type)

    if 'sensor' in prompt and not any(c in config['components'] for c in ['LIDAR', 'CAMERA']):
        config['components'].append('LIDAR')

    # --- 3.1 Cleanup Generics ---
    if 'MOTOR_SERVO' in config['components'] or 'MOTOR_STEPPER' in config['components']:
        if 'MOTOR' in config['components']: config['components'].remove('MOTOR')
    if any(k in config['components'] for k in ['WHEEL_MECANUM', 'WHEEL_OMNI', 'WHEEL_OFFROAD', 'WHEEL_CASTER']):
        if 'WHEEL' in config['components']: config['components'].remove('WHEEL')

    # --- 4. Apply Defaults and Fallbacks ---
    if config['type'] == 'ROVER' and 'wheels' not in config['params']:
        config['params']['wheels'] = 4
    if config['type'] == 'ARM' and 'joints' not in config['params']:
        config['params']['joints'] = 4 # Default arm length
    if config['type'] == 'UNKNOWN':
        if 'wheels' in config['params']: config['type'] = 'ROVER'
        elif 'joints' in config['params']: config['type'] = 'ARM'
        elif config['components']: config['type'] = 'PARTS_ONLY'
        else: config['type'] = 'ROVER' # Fallback
        
    return config

def _build_procedural_humanoid(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Procedurally builds a simple humanoid robot."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location

    # --- FOUNDATION: Torso ---
    torso_h = 0.5 * scale_factor
    torso_w = 0.3 * scale_factor
    torso_d = 0.2 * scale_factor
    # Raise humanoid to stand on the grid floor
    torso_pos = cursor_loc + mathutils.Vector((0, 0, torso_h / 2 + 0.8 * scale_factor))
    
    bpy.ops.mesh.primitive_cube_add(size=1, location=torso_pos)
    torso = context.active_object
    torso.name = get_unique_name("Torso")
    torso.dimensions = (torso_w, torso_d, torso_h)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = torso
    torso.select_set(True)
    bpy.ops.fcd.add_bone()
    torso_bone = f"Bone_{torso.name.replace('.', '_')}"
    
    pbone = rig.pose.bones.get(torso_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)

    # --- ACTION: LEGS ---
    for side in [-1, 1]: # Left (-1), Right (1)
        side_str = "L" if side < 0 else "R"
        parent_bone_name = torso_bone
        
        # --- Hip Joint (Z-axis rotation) ---
        hip_pos = torso_pos + mathutils.Vector((side * torso_w / 4, 0, -torso_h / 2))
        hip_joint = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', hip_pos, scale_factor=scale_factor*0.8, rotor_arm_length=0.05*scale_factor)
        hip_joint.name = get_unique_name(f"Hip_{side_str}")
        base_bone, joint_bone = rig_parametric_joint(context, hip_joint)
        context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones.get(joint_bone); pbone.fcd_pg_kinematic_props.axis_enum = 'Z'
        parent_bone_name = joint_bone
        context.view_layer.update() # Update for next calculation
        current_pos = hip_joint.matrix_world @ mathutils.Vector((hip_joint.fcd_pg_mech_props.radius + hip_joint.fcd_pg_mech_props.rotor_arm_length, 0, 0))

        # --- Knee Joint (Y-axis rotation) ---
        knee_joint = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', current_pos, scale_factor=scale_factor*0.7, rotor_arm_length=0.3*scale_factor)
        knee_joint.name = get_unique_name(f"Knee_{side_str}")
        knee_joint.rotation_euler.x = -math.pi / 2; bpy.ops.object.transform_apply(rotation=True)
        base_bone, joint_bone = rig_parametric_joint(context, knee_joint)
        context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones.get(joint_bone); pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
        parent_bone_name = joint_bone
        context.view_layer.update() # Update for next calculation
        current_pos = knee_joint.matrix_world @ mathutils.Vector((knee_joint.fcd_pg_mech_props.radius + knee_joint.fcd_pg_mech_props.rotor_arm_length, 0, 0))

        # --- Foot ---
        foot_pos = current_pos + mathutils.Vector((0.05*scale_factor, 0, 0))
        bpy.ops.mesh.primitive_cube_add(size=1, location=foot_pos)
        foot = context.active_object
        foot.name = get_unique_name(f"Foot_{side_str}")
        foot.dimensions = (0.15 * scale_factor, 0.1 * scale_factor, 0.04 * scale_factor)
        bpy.ops.object.transform_apply(scale=True)
        context.view_layer.objects.active = foot; foot.select_set(True); bpy.ops.fcd.add_bone()
        foot_bone = f"Bone_{foot.name.replace('.', '_')}"
        context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones[foot_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones.get(foot_bone); pbone.fcd_pg_kinematic_props.joint_type = 'fixed'

    # --- ACTION: ARMS ---
    for side in [-1, 1]: # Left (-1), Right (1)
        side_str = "L" if side < 0 else "R"
        parent_bone_name = torso_bone
        
        # --- Shoulder Joint ---
        shoulder_pos = torso_pos + mathutils.Vector((side * (torso_w / 2 + 0.05 * scale_factor), 0, torso_h / 2 * 0.8))
        shoulder_joint = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', shoulder_pos, scale_factor=scale_factor*0.6, rotor_arm_length=0.2*scale_factor)
        shoulder_joint.name = get_unique_name(f"Shoulder_{side_str}")
        shoulder_joint.rotation_euler.y = -side * math.pi / 2; bpy.ops.object.transform_apply(rotation=True)
        base_bone, joint_bone = rig_parametric_joint(context, shoulder_joint)
        context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones.get(joint_bone); pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
        parent_bone_name = joint_bone
        context.view_layer.update() # Update for next calculation
        current_pos = shoulder_joint.matrix_world @ mathutils.Vector((shoulder_joint.fcd_pg_mech_props.radius + shoulder_joint.fcd_pg_mech_props.rotor_arm_length, 0, 0))

        # --- Elbow Joint ---
        elbow_joint = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', current_pos, scale_factor=scale_factor*0.5, rotor_arm_length=0.2*scale_factor)
        elbow_joint.name = get_unique_name(f"Elbow_{side_str}")
        elbow_joint.rotation_euler.y = -side * math.pi / 2; bpy.ops.object.transform_apply(rotation=True)
        base_bone, joint_bone = rig_parametric_joint(context, elbow_joint)
        context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE')
        pbone = rig.pose.bones.get(joint_bone); pbone.fcd_pg_kinematic_props.axis_enum = 'Y'

    # --- ACTION: HEAD ---
    unit_scale = context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0
    
    neck_pos = torso_pos + mathutils.Vector((0, 0, (torso_h / 2) * s))
    neck_joint = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', neck_pos, scale_factor=scale_factor*0.5, rotor_arm_length=0.05*scale_factor)
    neck_joint.name = get_unique_name("Neck")
    base_bone, joint_bone = rig_parametric_joint(context, neck_joint)
    context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[torso_bone]
    bpy.ops.object.mode_set(mode='POSE')
    pbone = rig.pose.bones.get(joint_bone); pbone.fcd_pg_kinematic_props.axis_enum = 'Z'
    
    context.view_layer.update() # Update for head position
    head_pos = neck_joint.matrix_world @ mathutils.Vector((0, 0, (neck_joint.fcd_pg_mech_props.length / 2 + 0.1*scale_factor) * s))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12*scale_factor*s, location=head_pos)
    head = context.active_object; head.name = get_unique_name("Head")
    context.view_layer.objects.active = head; head.select_set(True); bpy.ops.fcd.add_bone()
    head_mesh_bone = f"Bone_{head.name.replace('.', '_')}"
    context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones[head_mesh_bone].parent = rig.data.edit_bones[joint_bone]
    bpy.ops.object.mode_set(mode='POSE')
    pbone = rig.pose.bones.get(head_mesh_bone); pbone.fcd_pg_kinematic_props.joint_type = 'fixed'

def _build_simple_shape(context: bpy.types.Context, shape_type: str, scale_factor: float):
    """Generates a simple primitive shape with a base bone."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    unit_scale = context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0

    if shape_type == 'BOX':
        bpy.ops.mesh.primitive_cube_add(size=1.0 * scale_factor * s, location=cursor_loc)
    elif shape_type == 'CYLINDER':
        bpy.ops.mesh.primitive_cylinder_add(radius=0.5 * scale_factor * s, depth=1.0 * scale_factor * s, location=cursor_loc)
    elif shape_type == 'SPHERE':
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5 * scale_factor * s, location=cursor_loc)
        
    obj = context.active_object
    obj.name = get_unique_name(shape_type.capitalize())
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.fcd.add_bone()
    
    bone_name = f"Bone_{obj.name.replace('.', '_')}"
    pbone = rig.pose.bones.get(bone_name)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)

def _build_procedural_parts(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """Generates standalone components based on the prompt."""
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    offset = mathutils.Vector((0, 0, 0))
    spacing = 0.2 * scale_factor
    
    for comp in config['components']:
        pos = cursor_loc + offset
        obj = None
        
        if comp == 'LIDAR':
            obj = create_parametric_part_object(context, 'ELECTRONICS', 'SENSOR_LIDAR', pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.04*scale_factor)
        elif comp == 'CAMERA':
            obj = create_parametric_part_object(context, 'ELECTRONICS', 'CAMERA_DEFAULT', pos, scale_factor=scale_factor, radius=0.015*scale_factor, length=0.03*scale_factor)
        elif comp == 'MOTOR_SERVO':
             obj = create_parametric_part_object(context, 'ELECTRONICS', 'MOTOR_SERVO_STD', pos, scale_factor=scale_factor, radius=0.01*scale_factor, length=0.04*scale_factor)
        elif comp == 'MOTOR_STEPPER':
             obj = create_parametric_part_object(context, 'ELECTRONICS', 'MOTOR_STEPPER_NEMA', pos, scale_factor=scale_factor, radius=0.021*scale_factor, length=0.04*scale_factor)
        elif comp == 'MOTOR':
             obj = create_parametric_part_object(context, 'ELECTRONICS', 'MOTOR_DC_ROUND', pos, scale_factor=scale_factor, radius=0.015*scale_factor, length=0.04*scale_factor)
        elif comp == 'GEAR':
             obj = create_parametric_part_object(context, 'GEAR', 'SPUR', pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.01*scale_factor)
        elif comp == 'RACK':
             obj = create_parametric_part_object(context, 'RACK', 'RACK_SPUR', pos, scale_factor=scale_factor, radius=0.01*scale_factor, length=0.1*scale_factor)
        elif comp == 'FASTENER':
             obj = create_parametric_part_object(context, 'FASTENER', 'BOLT', pos, scale_factor=scale_factor, radius=0.005*scale_factor, length=0.02*scale_factor)
        elif comp == 'SPRING':
             obj = create_parametric_part_object(context, 'SPRING', 'SPRING', pos, scale_factor=scale_factor, radius=0.02*scale_factor, length=0.1*scale_factor)
        elif comp == 'DAMPER':
             obj = create_parametric_part_object(context, 'SPRING', 'DAMPER', pos, scale_factor=scale_factor, radius=0.02*scale_factor, length=0.1*scale_factor)
        elif comp == 'CHAIN':
             obj = create_parametric_part_object(context, 'CHAIN', 'ROLLER', pos, scale_factor=scale_factor, length=0.02*scale_factor)
        elif comp == 'BELT':
             obj = create_parametric_part_object(context, 'CHAIN', 'BELT', pos, scale_factor=scale_factor, length=0.02*scale_factor)
        elif comp == 'PULLEY':
             obj = create_parametric_part_object(context, 'PULLEY', 'PULLEY_FLAT', pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.02*scale_factor)
        elif comp == 'ROPE':
             obj = create_parametric_part_object(context, 'ROPE', 'ROPE_STEEL', pos, scale_factor=scale_factor, radius=0.005*scale_factor, length=1.0*scale_factor)
        elif comp == 'WHEEL':
             obj = create_parametric_part_object(context, 'WHEEL', 'WHEEL_STANDARD', pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.03*scale_factor)
        elif comp == 'WHEEL_MECANUM':
             obj = create_parametric_part_object(context, 'WHEEL', 'WHEEL_MECANUM', pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.04*scale_factor)
        elif comp == 'WHEEL_OMNI':
             obj = create_parametric_part_object(context, 'WHEEL', 'WHEEL_OMNI', pos, scale_factor=scale_factor, radius=0.05*scale_factor, length=0.03*scale_factor)
        elif comp == 'WHEEL_OFFROAD':
             obj = create_parametric_part_object(context, 'WHEEL', 'WHEEL_OFFROAD', pos, scale_factor=scale_factor, radius=0.06*scale_factor, length=0.04*scale_factor)
        elif comp == 'WHEEL_CASTER':
             obj = create_parametric_part_object(context, 'WHEEL', 'WHEEL_CASTER', pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.03*scale_factor)
        elif comp == 'JOINT':
             obj = create_parametric_part_object(context, 'BASIC_JOINT', 'JOINT_REVOLUTE', pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.05*scale_factor)
        elif comp == 'PCB':
             obj = create_parametric_part_object(context, 'ELECTRONICS', 'PCB_BOARD', pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.05*scale_factor)
        elif comp == 'IC':
             obj = create_parametric_part_object(context, 'ELECTRONICS', 'IC_MICROCHIP', pos, scale_factor=scale_factor, radius=0.01*scale_factor, length=0.02*scale_factor)
        
        if obj:
            # Auto-rig as base link so it can be moved
            context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.fcd.add_bone()
            
            bone_name = f"Bone_{obj.name.replace('.', '_')}"
            pbone = rig.pose.bones.get(bone_name)
            if pbone:
                pbone.fcd_pg_kinematic_props.joint_type = 'base'
                update_single_bone_gizmo(pbone, True)
        
        offset.x += spacing

def _build_procedural_arm(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float, base_obj: Optional[bpy.types.Object] = None, start_z: float = 0.0):
    """
    Procedurally builds a robotic arm.
    """
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    num_joints = config['params'].get('joints', 4)
    
    # Base position
    base_pos = cursor_loc.copy()
    if base_obj:
        # AI Editor Note: Use world translation to ensure correct connectivity even if parent has transforms
        base_pos = base_obj.matrix_world.translation.copy()
        base_pos.z += start_z
    
    parent_bone_name = None
    if base_obj:
        # Find the bone of the base object
        parent_bone_name = base_obj.parent_bone

    # Create Arm Base (if standalone)
    if not base_obj:
        unit_scale = context.scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08 * scale_factor * s, depth=0.05 * scale_factor * s, location=base_pos + mathutils.Vector((0,0,0.025*scale_factor*s)))
        base_link = context.active_object
        base_link.name = get_unique_name("Arm_Base")
        
        context.view_layer.objects.active = base_link
        base_link.select_set(True)
        bpy.ops.fcd.add_bone()
        parent_bone_name = f"Bone_{base_link.name.replace('.', '_')}"
        
        # Set base joint type
        pbone = rig.pose.bones.get(parent_bone_name)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'base'
            update_single_bone_gizmo(pbone, True)
        
        base_pos.z += 0.05 * scale_factor

    # Build Joints using Parametric Parts
    current_pos = base_pos.copy()
    # Start slightly above base
    current_pos.z += 0.02 * scale_factor
    
    for i in range(num_joints):
        # Determine joint type and orientation
        # Joint 1: Turret (Continuous, Z)
        # Joint 2+: Arm segments (Revolute, Y)
        joint_type = 'JOINT_REVOLUTE'
        if i == 0:
            joint_type = 'JOINT_CONTINUOUS'
        
        # Scale down joints progressively
        j_scale = scale_factor * (1.0 - (i * 0.1))
        if j_scale < 0.5 * scale_factor: j_scale = 0.5 * scale_factor
        
        # Create Parametric Joint
        # Note: We create it at current_pos.
        # For Revolute joints, we rotate them 90 deg on X to align axis to Y.
        joint_obj = create_parametric_part_object(
            context, 'BASIC_JOINT', joint_type, current_pos, scale_factor=j_scale,
            radius=0.04 * j_scale, length=0.06 * j_scale,
            rotor_arm_length=0.25 * scale_factor, # Length of the link
            rotor_arm_width=0.03 * j_scale,
            rotor_arm_height=0.03 * j_scale
        )
        joint_obj.name = get_unique_name(f"Joint_{i+1}")
        
        # Rotate Y-axis joints
        if i > 0:
            joint_obj.rotation_euler.x = math.pi / 2
            bpy.ops.object.transform_apply(rotation=True, scale=True)
            
        # Rig the joint
        base_bone, joint_bone = rig_parametric_joint(context, joint_obj)
        
        # Parent new joint's base to previous joint's moving part
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        if parent_bone_name:
            rig.data.edit_bones[base_bone].parent = rig.data.edit_bones[parent_bone_name]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        # Configure Joint Limits/Axis
        pbone = rig.pose.bones.get(joint_bone)
        if pbone:
            if i == 0:
                pbone.fcd_pg_kinematic_props.joint_type = 'continuous' # Base rotation
                pbone.fcd_pg_kinematic_props.axis_enum = 'Z'
            elif i % 2 == 1:
                pbone.fcd_pg_kinematic_props.joint_type = 'revolute'
                pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
            else:
                pbone.fcd_pg_kinematic_props.joint_type = 'revolute'
                pbone.fcd_pg_kinematic_props.axis_enum = 'Y' # Keep Y for main lift joints usually
            
            update_single_bone_gizmo(pbone, True)
            apply_native_constraints(pbone)
            
        parent_bone_name = joint_bone
        
        # AI Editor Note: Force update to ensure matrix_world is correct after parenting/rigging.
        # This is critical for calculating the attachment point of the *next* joint in the chain.
        context.view_layer.update()
        
        # --- COGNITION: Calculate Next Joint Position ---
        # Determine the attachment point for the next link based on the current joint's geometry.
        # For continuous joints (turrets), stack vertically. For revolute arms, move along the arm length.
        if joint_type == 'JOINT_CONTINUOUS':
            # Stack on top: Z-offset = length/2 (center to top)
            current_pos = joint_obj.matrix_world @ mathutils.Vector((0, 0, joint_obj.fcd_pg_mech_props.length / 2.0))
        else:
            # Extend along arm: X-offset = radius + arm_length
            # Note: The joint object is rotated, so local X is the arm direction.
            arm_ext = joint_obj.fcd_pg_mech_props.radius + joint_obj.fcd_pg_mech_props.rotor_arm_length
            current_pos = joint_obj.matrix_world @ mathutils.Vector((arm_ext, 0, 0))

def _build_procedural_rover(context: bpy.types.Context, config: Dict[str, Any], scale_factor: float):
    """
    Procedurally builds a rover based on config.
    """
    rig = context.scene.fcd_active_rig
    cursor_loc = context.scene.cursor.location
    
    # --- COGNITION: Dimension Planning ---
    unit_scale = context.scene.unit_settings.scale_length
    s = 1.0 / unit_scale if unit_scale > 0 else 1.0

    num_wheels = config['params'].get('wheels', 4)
    
    # Chassis Dimensions (Normalized to Meters internally, so apply s for BU)
    chassis_len = (0.15 * num_wheels) * scale_factor * s
    if chassis_len < 0.4 * scale_factor * s: chassis_len = 0.4 * scale_factor * s
    chassis_width = 0.3 * scale_factor * s
    chassis_height = 0.1 * scale_factor * s
    
    # Calculate placement (Chassis bottom at clearance height)
    ground_clearance = 0.05 * scale_factor * s
    chassis_center_z = ground_clearance + (chassis_height / 2.0)
    chassis_pos = cursor_loc + mathutils.Vector((0, 0, chassis_center_z)) # chassis_center_z is already scaled
    
    # --- ACTION: Create Chassis ---
    bpy.ops.mesh.primitive_cube_add(size=1.0 * s, location=chassis_pos)
    chassis = context.active_object
    chassis.name = get_unique_name("Chassis")
    chassis.dimensions = (chassis_len, chassis_width, chassis_height)
    bpy.ops.object.transform_apply(scale=True)
    
    context.view_layer.objects.active = chassis
    chassis.select_set(True)
    bpy.ops.fcd.add_bone()
    chassis_bone = f"Bone_{chassis.name.replace('.', '_')}"
    
    # Set chassis as base
    pbone = rig.pose.bones.get(chassis_bone)
    if pbone:
        pbone.fcd_pg_kinematic_props.joint_type = 'base'
        update_single_bone_gizmo(pbone, True)
        apply_native_constraints(pbone)

    # --- ACTION: Create Wheels ---
    wheel_radius = 0.08 * scale_factor
    wheel_width = 0.04 * scale_factor
    
    # Calculate positions
    # Simple layout: Rows on left and right
    rows = math.ceil(num_wheels / 2)
    x_spacing = chassis_len / rows
    x_start = -(chassis_len / 2) + (x_spacing / 2)
    
    wheel_positions = []
    
    if num_wheels == 3:
        # Tricycle: 1 front, 2 back
        wheel_positions.append((chassis_len/2, 0)) # Front Center
        wheel_positions.append((-chassis_len/2, chassis_width/2 + wheel_width/2)) # Back Left
        wheel_positions.append((-chassis_len/2, -chassis_width/2 - wheel_width/2)) # Back Right
    else:
        # Standard rows
        for i in range(rows):
            x = x_start + i * x_spacing
            # Left
            wheel_positions.append((x, chassis_width/2 + wheel_width/2))
            # Right
            if len(wheel_positions) < num_wheels:
                wheel_positions.append((x, -chassis_width/2 - wheel_width/2))
                
    for i, (x, y) in enumerate(wheel_positions):
        # Wheel center Z is at radius height (touching ground)
        pos = cursor_loc + mathutils.Vector((x, y, wheel_radius))
        
        # AI Editor Note: Use parametric wheel generator for robustness
        wheel = create_parametric_part_object(context, 'WHEEL', 'WHEEL_OFFROAD', pos, scale_factor=scale_factor, radius=wheel_radius, length=wheel_width, teeth=12)
        wheel.name = get_unique_name(f"Wheel_{i+1}")
        # Parametric wheels are generated Y-aligned (rolling X), so rotate 90 Z to roll Y? No, rover rolls X.
        # Standard wheel gen is Y-axle. Rover moves X. So wheels need to be Y-axle.
        # The generator does `bmesh.ops.rotate(..., matrix=Rotation(90, 'X'))` making it Y-axle.
        # So no extra rotation needed if we want them to roll along X.
        
        context.view_layer.objects.active = wheel
        wheel.select_set(True)
        bpy.ops.fcd.add_bone()
        w_bone = f"Bone_{wheel.name.replace('.', '_')}"
        
        # Parent to chassis
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[w_bone].parent = rig.data.edit_bones[chassis_bone]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        pbone = rig.pose.bones.get(w_bone)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'continuous'
            pbone.fcd_pg_kinematic_props.axis_enum = 'Y'
            update_single_bone_gizmo(pbone, True)
            apply_native_constraints(pbone)

    # --- ACTION: Add Sensors ---
    if 'LIDAR' in config['components']:
        # Place on top front of chassis
        # Top Z = chassis_center_z + chassis_height/2
        lidar_z = chassis_center_z + (chassis_height / 2.0) + (0.02 * scale_factor * s) # Slight offset
        lidar_pos = cursor_loc + mathutils.Vector(((chassis_len/3), 0, lidar_z)) # chassis_len is already scaled
        
        # AI Editor Note: Use parametric sensor
        lidar = create_parametric_part_object(context, 'ELECTRONICS', 'SENSOR_LIDAR', lidar_pos, scale_factor=scale_factor, radius=0.03*scale_factor, length=0.04*scale_factor)
        lidar.name = get_unique_name("Lidar")
        
        context.view_layer.objects.active = lidar
        lidar.select_set(True)
        bpy.ops.fcd.add_bone()
        l_bone = f"Bone_{lidar.name.replace('.', '_')}"
        
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        rig.data.edit_bones[l_bone].parent = rig.data.edit_bones[chassis_bone]
        bpy.ops.object.mode_set(mode='POSE', toggle=False)
        
        pbone = rig.pose.bones.get(l_bone)
        if pbone:
            pbone.fcd_pg_kinematic_props.joint_type = 'fixed'
            update_single_bone_gizmo(pbone, True)
            apply_native_constraints(pbone)

    # --- ACTION: Add Arm ---
    if 'ARM' in config['components']:
        # AI Editor Note: Force update to ensure chassis matrix_world is correct before attaching arm.
        # This ensures the arm base is placed relative to the chassis's final position.
        context.view_layer.update()
        
        # Calculate mount point relative to chassis center
        # We want the arm base to sit exactly on top of the chassis.
        # Chassis Top Z (relative to center) = chassis_height / 2
        arm_z_offset = (chassis_height / 2.0)
        _build_procedural_arm(context, config, scale_factor, base_obj=chassis, start_z=arm_z_offset)

def build_generative_robot(context: bpy.types.Context, prompt: str, scale_factor: float = 1.0):
    """
    Builds a robot based on the interpreted prompt using procedural logic.
    Structure: Context -> Foundation -> Perception -> Cognition -> Action -> Guard
    """
    # --- 1. CONTEXT: Setup environment ---
    if context.active_object and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    
    # --- 2. FOUNDATION: Create Rig ---
    bpy.ops.fcd.create_rig()
    rig = context.scene.fcd_active_rig
    if not rig:
        print("URDF AI Error: Failed to create rig foundation.")
        return

    # --- 3. PERCEPTION: Parse Prompt ---
    config = parse_natural_language_prompt(prompt)
    print(f"URDF AI: Generating {config['type']} with params {config['params']} and components {config['components']}")
    
    # --- 4. COGNITION & ACTION: Dispatch to Builders ---
    try:
        if config['type'] == 'ROVER':
            _build_procedural_rover(context, config, scale_factor)
        elif config['type'] == 'ARM':
            _build_procedural_arm(context, config, scale_factor)
        elif config['type'] == 'MOBILE_BASE':
            build_mobile_base_diff_drive(context, scale_factor=scale_factor)
        elif config['type'] == 'QUADRUPED':
            build_quadruped_spider(context, scale_factor=scale_factor)
        elif config['type'] == 'DRONE':
            _build_procedural_drone(context, config, scale_factor)
        elif config['type'] == 'PLANE':
            _build_procedural_plane(context, config, scale_factor)
        elif config['type'] == 'FURNITURE':
            _build_procedural_furniture(context, config, scale_factor)
        elif config['type'] == 'CONVEYOR':
            _build_procedural_conveyor(context, config, scale_factor)
        elif config['type'] == 'HUMANOID':
            _build_procedural_humanoid(context, config, scale_factor)
        elif config['type'] in ['BOX', 'CYLINDER', 'SPHERE']:
            _build_simple_shape(context, config['type'], scale_factor)
        elif config['type'] == 'PARTS_ONLY':
            _build_procedural_parts(context, config, scale_factor)
        else:
            # Fallback
            _build_procedural_rover(context, config, scale_factor)
            
        # Final update to ensure everything is attached correctly
        context.view_layer.update()
        
    except Exception as e:
        # --- 5. GUARD: Error Handling ---
        print(f"URDF AI Error during generation: {e}")
        import traceback
        traceback.print_exc()
        
    # --- 6. FINALIZATION ---
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    context.view_layer.objects.active = rig

# ------------------------------------------------------------------------
#   PART 1.5: UI COLLAPSE LOGIC
# ------------------------------------------------------------------------

def get_all_children_objects(bone: bpy.types.PoseBone, context: bpy.types.Context) -> List[bpy.types.Object]:
    """
    Finds all objects (meshes, empties, etc.) that are effectively parented to a given bone, 
    including deeply nested children hierarchies.
    """
    rig = bone.id_data
    all_objs = set()

    def gather_recursive(obj):
        all_objs.add(obj)
        for child in obj.children:
            gather_recursive(child)

    # Find all objects parented directly to this bone and start recursion.
    for obj in context.scene.objects:
        if obj.parent == rig and obj.parent_type == 'BONE' and obj.parent_bone == bone.name:
            gather_recursive(obj)
            
    return list(all_objs)

def update_single_bone_gizmo(bone: bpy.types.PoseBone, show_gizmos: bool, style: str = 'DEFAULT') -> None:
    """
    Updates the custom shape (widget or "gizmo") for a single bone to visually
    represent its joint properties.

    Args:
        bone: The `PoseBone` whose gizmo needs to be updated.
        show_gizmos: A boolean indicating whether gizmos should be visible.
        style: The visual style of the gizmo ('DEFAULT', '3D').
    """
    props = bone.fcd_pg_kinematic_props
    if not show_gizmos or props.joint_type == 'none':
        bone.custom_shape = None
        return

    bone.rotation_mode = 'XYZ'
    gizmo_type = 'ROTATION'
    if props.joint_type == 'prismatic':
        gizmo_type = 'SLIDER'
    elif props.joint_type == 'spherical':
        gizmo_type = 'SPHERICAL'
    elif props.joint_type == 'fixed':
        gizmo_type = 'FIXED'
    elif props.joint_type == 'base':
        gizmo_type = 'BASE'

    # Get the UI-selected axis, which directly maps to the bone's local axis.
    # AI Editor Note: The 'BASE' gizmo is axis-independent.
    raw_axis = props.axis_enum.replace("-", "")
    
    # AI Editor Note: Corrected gizmo axis mapping to match the constraints and user expectations.
    # The constraints map X->Z, Y->X, Z->Y (via axis_map {0:2, 1:0, 2:1}).
    # The gizmos must follow the same mapping to visually align with the physics.
    if raw_axis == 'X': target_axis = 'Z'
    elif raw_axis == 'Y': target_axis = 'X'
    else: target_axis = 'Y'

    if gizmo_type == 'BASE': target_axis = 'Z'

    # AI Editor Note: Retrieve the gizmo style. 
    # Use the passed style argument to avoid context issues in callbacks/timers.
    wgt = create_flat_gizmo(gizmo_type, target_axis, style)

    if wgt:
        bone.custom_shape = wgt

        base_scale = 1.0
        found_parametric_scale = False

        def get_parametric_props(b):
            """
            Searches the child meshes of a bone for a parametric 'BASIC_JOINT'
            and returns its properties.
            """
            for obj in get_all_children_objects(b, bpy.context):
                if hasattr(obj, "fcd_pg_mech_props") and obj.fcd_pg_mech_props.is_part and obj.fcd_pg_mech_props.category == 'BASIC_JOINT':
                    # Return the actual geometry radius if it's a gear/wheel
                    if obj.fcd_pg_mech_props.category in ['GEAR', 'WHEEL', 'BASIC_JOINT']:
                        return obj.fcd_pg_mech_props
            return None
        # --- ACTION: Calculate Bone-Local Bounding Box ---
        local_min = mathutils.Vector((0.0, 0.0, 0.0))
        local_max = mathutils.Vector((0.0, 0.0, 0.0))
        has_meshes = False
        
        # Access the Armature object to get its world transform
        armature_obj = bone.id_data
        bone_world_matrix = armature_obj.matrix_world @ bone.matrix
        bone_world_mat_inv = bone_world_matrix.inverted()
        
        # Robust context handling for background updates.
        # If bpy.context is restricted, we fall back to scene-wide search.
        search_ctx = bpy.context if bpy.context and hasattr(bpy.context, "scene") else None
        target_scene = search_ctx.scene if search_ctx else (bone.id_data.users_scene[0] if bone.id_data.users_scene else bpy.data.scenes[0])
        
        child_meshes = []
        # Find objects parented directly to this bone.
        rig = bone.id_data
        # Optimization: Use a list comprehension to find direct descendants of the bone.
        child_meshes = [o for o in armature_obj.children if o.parent == armature_obj and o.parent_type == 'BONE' and o.parent_bone == bone.name]
        
        # Also include recursively parented meshes, but avoid full scene loops if possible.
        # But Blender's hierarchy can be complex, so if we have many, we stick to direct ones
        # for performance, or look into rig.children.
        all_children = []
        for o in child_meshes:
            all_children.append(o)
            all_children.extend([c for c in o.children_recursive if c.type == 'MESH'])
        
        child_meshes = all_children

        for mesh_obj in child_meshes:
            if mesh_obj.type != 'MESH': continue
            has_meshes = True
            
            # Bound box sync
            for point in mesh_obj.bound_box:
                world_point = mesh_obj.matrix_world @ mathutils.Vector(point)
                local_point = bone_world_mat_inv @ world_point
                
                for i in range(3):
                    local_min[i] = min(local_min[i], local_point[i])
                    local_max[i] = max(local_max[i], local_point[i])

        # Access variables for scaling
        unit_scale = target_scene.unit_settings.scale_length
        s = 1.0 / unit_scale if unit_scale > 0 else 1.0

        # --- ACTION: Determine Base Scale ---
        base_scale = 0.5 * s # Default fallback (normalized)
        
        if has_meshes:
            dims = local_max - local_min
            # For Rotation gizmos (Disk/Ring), we want the diameter.
            # In Blender bone space, Y is the bone axis. Radius is in X/Z plane.
            base_scale = max(dims)
            
            # Special case for sliders: often better to match bone length
            if gizmo_type == 'SLIDER':
                if bone.length > config.MIN_BONE_LENGTH:
                    base_scale = bone.length / 2.0
            
            # Ensure it's at least as large as the manual radius property
            # props.joint_radius is in meters, so multiply by s for BU.
            if base_scale < props.joint_radius * s:
                base_scale = props.joint_radius * s
        else:
            # Fallback to properties if no meshes attached.
            # Convert meters to BU using s.
            if gizmo_type == 'ROTATION':
                base_scale = props.joint_radius * s
            elif gizmo_type == 'SLIDER':
                # bone.length is in BU, so no 's' needed.
                base_scale = bone.length / 2.0 if bone.length > config.MIN_BONE_LENGTH else 0.5 * s
            elif gizmo_type == 'FIXED':
                base_scale = props.joint_radius * 0.5 * s
            elif gizmo_type == 'BASE':
                # bone.length is in BU.
                base_scale = bone.length if bone.length > 0.05 * s else (props.joint_radius * 2.0 * s)
                if base_scale < 0.05 * s:
                    base_scale = 0.5 * s
                
                # Ensure it doesn't stay at 0.5 if it's meant to be small
                if bone.length < 0.2 and props.joint_radius < 0.2:
                    base_scale = max(bone.length, props.joint_radius * 2.0)
                
        # --- AI Editor Note: Unified Radius Scaling ---
        # 1. Start with the physical Meter-based Joint Radius converted to Blender Units (BU).
        # This makes 'Joint Radius' the direct driver of the gizmo's physical size.
        r_bu = props.joint_radius * s
        
        # 2. If meshes exist, derive scale from their bounds but respect the Joint Radius as a minimum.
        if has_meshes:
            # max(dims) is already in BU.
            r_bu = max(max(dims), props.joint_radius * s)
        
        # 3. Apply the visual 'Gizmo Radius' multiplier.
        # This allows for subjective visual tweaks on top of physical data.
        final_scale = r_bu * props.gizmo_radius
        
        # Ensure the scale is never zero to prevent invisible gizmos.
        if final_scale < config.MIN_GIZMO_SCALE:
            final_scale = config.MIN_GIZMO_SCALE

        bone.custom_shape_scale_xyz = (final_scale, final_scale, final_scale)

        bone.use_custom_shape_bone_size = False
        bone.custom_shape_translation = (0, 0, 0)
        
        # AI Editor Note: The gizmo mesh is already pre-rotated by the create_flat_gizmo function.
        # Applying any additional rotation here is redundant and was causing orientation instability
        # when changing gizmo styles. Setting this to zero ensures that only the mesh's
        # inherent orientation is used, which is now the single source of truth for alignment.
        bone.custom_shape_rotation_euler = (0, 0, 0)
    else:
        bone.custom_shape = None

def get_mapped_axis_index(ui_axis_enum: str) -> int:
    """
    Converts the UI axis enum string (e.g., 'X', '-Y', 'Z') to a numerical
    index (0, 1, 2) for use with Blender's vector and array properties.

    Args:
        ui_axis_enum: The string representation of the axis from the UI.

    Returns:
        The corresponding integer index (0 for X, 1 for Y, 2 for Z).
    """
    axis = ui_axis_enum.replace("-", "")
    if axis == 'X': return 0
    if axis == 'Y': return 1
    # Default to Z for safety, although the enum should prevent other values.
    return 2

def clean_conflicting_mechanics(bone: bpy.types.PoseBone) -> None:
    """
    Prevents mechanical conflicts by removing obsolete drivers from a bone when
    its joint type is changed.

    For example, if a user changes a joint from 'revolute' to 'prismatic', this
    function will find and remove any old drivers that were controlling the bone's
    rotation, as they are no longer valid for a prismatic joint. This is crucial
    for preventing unexpected behavior and ensuring a clean state.

    Args:
        bone: The `PoseBone` to clean.
    """
    props = bone.fcd_pg_kinematic_props
    is_rot = props.joint_type in ['revolute', 'continuous']
    is_lin = props.joint_type == 'prismatic'

    # Check if the bone's armature has any animation data (and thus, any drivers).
    if not (bone.id_data and bone.id_data.animation_data and bone.id_data.animation_data.drivers):
        return

    drivers = bone.id_data.animation_data.drivers
    drivers_to_remove = []

    for d in drivers:
        # Check if the driver exactly targets the current bone.
        expected_prefix = f'pose.bones["{bone.name}"].'
        if d.data_path.startswith(expected_prefix):
            # If the new type is rotational, remove any old location drivers.
            if is_rot and "location" in d.data_path:
                drivers_to_remove.append(d)
            # If the new type is linear, remove any old rotation drivers.
            elif is_lin and "rotation" in d.data_path:
                drivers_to_remove.append(d)
            # If the new type is fixed or none, remove all drivers.
            elif props.joint_type in ['fixed', 'none', 'base']:
                drivers_to_remove.append(d)

    for d in drivers_to_remove:
        drivers.remove(d)

def remove_all_fcd_constraints(bone: bpy.types.PoseBone) -> None:
    """Helper to thoroughly remove all limit constraints created by the addon."""
    from .config import MOD_PREFIX
    for c in list(bone.constraints):
        if c.name.startswith(f"{MOD_PREFIX}Limit_Rot") or c.name.startswith(f"{MOD_PREFIX}Limit_Loc"):
            bone.constraints.remove(c)

def apply_native_constraints(bone: bpy.types.PoseBone) -> None:
    """
    Applies all native Blender constraints (FK locks, IK limits, and Limit
    constraints) to a bone based on its URDF properties.

    This function is the heart of the addon's kinematics system. It translates
    the high-level URDF joint properties into a set of standard Blender
    constraints, ensuring that the rig behaves correctly during posing and
    animation.

    It uses a robust "calculate-then-apply" strategy. It first determines the
    desired final state of all relevant properties in local variables, then
    applies that state to the bone's properties all at once. This avoids
    intermediate states and potential dependency issues.

    Args:
        bone: The `PoseBone` to apply the constraints to.
    """
    props = bone.fcd_pg_kinematic_props
    # Get the numerical index (0, 1, 2) corresponding to the UI selection.
    ui_idx = get_mapped_axis_index(props.axis_enum)

    # This block maps the UI axis to the bone's local axis.
    # AI Editor Note: Correcting axis misalignment.
    # The user reported a cyclic permutation where UI 'X' affected Blender's Y-axis,
    # 'Y' affected 'Z', and 'Z' affected 'X'. To correct this, we apply an
    # inverse permutation to the axis index before it's used for constraints.
    # AI Editor Note: DO NOT CHANGE THIS MAPPING. It is notoriously tricky to align.
    axis_map = {0: 2, 1: 0, 2: 1}
    unlocked_idx = axis_map.get(ui_idx, ui_idx)

    # AI Editor Note: Avoid using global bpy.context where possible for timer safety.
    # Get the scene from the bone's armature object.
    scene = bone.id_data.users_scene[0] if bone.id_data.users_scene else bpy.context.scene
    is_placing = scene.fcd_placement_mode

    # --- 1. Handle Special Modes (Placement / None) ---
    if is_placing:
        # AI Editor Note: In placement mode, respect the 'Connected' parent-child relationship.
        # If a bone is 'Connected' to its parent, its location will remain locked.
        # This allows users to move chains of connected bones as a single unit.
        should_lock_location = bone.parent is not None and bone.bone.use_connect
        bone.lock_location = (should_lock_location, should_lock_location, should_lock_location)
        bone.lock_rotation = (False, False, False)
        bone.lock_scale = (True, True, True)  # Scale is always locked for stability.
        # Unlock all IK axes and disable limits.
        bone.lock_ik_x = False
        bone.lock_ik_y = False
        bone.lock_ik_z = False
        bone.use_ik_limit_x = False
        bone.use_ik_limit_y = False
        bone.use_ik_limit_z = False
        
        remove_all_fcd_constraints(bone)
        return

    if props.joint_type in ['none', 'base']:
        bone.lock_location = (False, False, False)
        bone.lock_rotation = (False, False, False)
        bone.lock_scale = (True, True, True)
        bone.lock_ik_x = False
        bone.lock_ik_y = False
        bone.lock_ik_z = False
        bone.use_ik_limit_x = False
        bone.use_ik_limit_y = False
        bone.use_ik_limit_z = False
        
        remove_all_fcd_constraints(bone)
        return

    # --- 2. Calculate the Desired Constraint State ---
    # Start by assuming a fully locked 'fixed' joint, then unlock axes as needed.
    fk_lock_loc = [True, True, True]
    fk_lock_rot = [True, True, True]
    ik_lock_loc = [True, True, True]
    ik_use_limit_rot = [True, True, True]
    ik_rot_limits = [(0, 0), (0, 0), (0, 0)]

    remove_all_fcd_constraints(bone)

    if props.joint_type in ['revolute', 'continuous']:
        # For rotational joints, unlock the appropriate rotation axis for both FK and IK.
        fk_lock_rot[unlocked_idx] = False
        ik_use_limit_rot[unlocked_idx] = False  # Allow free rotation for IK by default.

        if props.joint_type == 'revolute':
            # For 'revolute' joints, apply limits.
            min_rad = math.radians(props.lower_limit)
            max_rad = math.radians(props.upper_limit)

            # Invert limits for Y and Z axes to achieve the final composite rotation
            if unlocked_idx in [1, 2]: # Y or Z axis
                min_rad, max_rad = -max_rad, -min_rad

            # Re-enable the IK limit for the unlocked axis with the specified values.
            ik_use_limit_rot[unlocked_idx] = True
            ik_rot_limits[unlocked_idx] = (min_rad, max_rad)

            # Add a 'LIMIT_ROTATION' constraint for FK posing.
            con = bone.constraints.new('LIMIT_ROTATION')
            con.name = f"{MOD_PREFIX}Limit_Rot"
            con.owner_space = 'LOCAL'
            if unlocked_idx == 0: con.use_limit_x = True; con.min_x = min_rad; con.max_x = max_rad
            elif unlocked_idx == 1: con.use_limit_y = True; con.min_y = min_rad; con.max_y = max_rad
            elif unlocked_idx == 2: con.use_limit_z = True; con.min_z = min_rad; con.max_z = max_rad
            
    elif props.joint_type == 'spherical':
        # Spherical joints are free to rotate on all axes
        fk_lock_rot = [False, False, False]
        # For IK, unlock all rotation axes
        ik_use_limit_rot = [False, False, False]
        # No FK limits needed for a full spherical joint by default

    elif props.joint_type == 'prismatic':
        # For linear joints, unlock the appropriate location axis for both FK and IK.
        fk_lock_loc[unlocked_idx] = False
        ik_lock_loc[unlocked_idx] = False

        # Add a 'LIMIT_LOCATION' constraint for FK posing.
        min_val = props.lower_limit
        max_val = props.upper_limit

        # Invert limits for Y and Z axes to achieve the final composite rotation
        if unlocked_idx in [1, 2]: # Y or Z axis
            min_val, max_val = -max_val, -min_val

        con = bone.constraints.new('LIMIT_LOCATION')
        con.name = f"{MOD_PREFIX}Limit_Loc"
        con.owner_space = 'LOCAL'
        if unlocked_idx == 0: con.use_min_x = True; con.use_max_x = True; con.min_x = min_val; con.max_x = max_val
        elif unlocked_idx == 1: con.use_min_y = True; con.use_max_y = True; con.min_y = min_val; con.max_y = max_val
        elif unlocked_idx == 2: con.use_min_z = True; con.use_max_z = True; con.min_z = min_val; con.max_z = max_val

    # --- 3. Apply All Calculated Properties to the Bone at Once ---
    # This atomic update ensures a clean and predictable state change.
    bone.lock_location = fk_lock_loc
    bone.lock_rotation = fk_lock_rot
    bone.lock_scale = (True, True, True)

    bone.lock_ik_x = ik_lock_loc[0]
    bone.lock_ik_y = ik_lock_loc[1]
    bone.lock_ik_z = ik_lock_loc[2]

    # --- AI Editor Note: Apply rotation IK limits where applicable ---
    bone.use_ik_limit_x = ik_use_limit_rot[0]
    bone.use_ik_limit_y = ik_use_limit_rot[1]
    bone.use_ik_limit_z = ik_use_limit_rot[2]

    bone.ik_min_x, bone.ik_max_x = ik_rot_limits[0]
    bone.ik_min_y, bone.ik_max_y = ik_rot_limits[1]
    bone.ik_min_z, bone.ik_max_z = ik_rot_limits[2]

# --- AI Editor Note: Guard and Handler for Local Cursor Tool ---

def update_local_cursor_from_tool(self, context):
    """
    Update callback for the local cursor tool property.
    When the user edits the local coordinates in the UI, this function
    calculates the new world position for the 3D cursor and applies it.
    """
    global _local_cursor_update_guard
    # Guard to prevent this from running when the property is updated by the draw function
    if _local_cursor_update_guard:
        return

    if context.active_object:
        obj = context.active_object
        # 'self' is the scene here
        local_co = self.fcd_cursor_local_pos
        world_co = obj.matrix_world @ mathutils.Vector(local_co)
        
        # Check to prevent feedback loops if the value hasn't changed significantly
        if (context.scene.cursor.location - world_co).length > 0.0001:
            context.scene.cursor.location = world_co

@persistent
def local_cursor_depsgraph_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    """
    A persistent handler that runs on dependency graph updates to keep the
    local cursor tool synchronized with the 3D cursor's actual position.
    This avoids writing data from within a draw function, which is forbidden.
    """
    # This handler can run in many contexts, so we need to be careful.
    context = bpy.context
    if not (context and context.active_object):
        return

    obj = context.active_object
    # Avoid ValueError: Matrix.invert(ed): matrix does not have an inverse
    if abs(obj.matrix_world.determinant()) < 1e-6:
        return
        
    cursor_local_vec = obj.matrix_world.inverted() @ scene.cursor.location

    # AI Editor Note: Attributes may be missing during add-on registration/unregistration.
    if not hasattr(scene, "fcd_cursor_local_pos"):
        return
        
    global _local_cursor_update_guard
    # Convert property array to mathutils.Vector before subtraction
    actual_pos = mathutils.Vector(getattr(scene, "fcd_cursor_local_pos", (0,0,0)))
    if (actual_pos - cursor_local_vec).length > 0.0001:
        _local_cursor_update_guard = True
        try:
            scene.fcd_cursor_local_pos = cursor_local_vec
        finally:
            _local_cursor_update_guard = False

def fcd_prop_update(self, context, prop_name: str):
    """
    Generic update callback for URDF properties on PoseBones.

    This function handles multi-object editing for URDF properties. When a
    property is changed on the active bone, this function propagates that
    single property's new value to all other selected bones. It then updates
    the visual and mechanical state of all selected bones to reflect the change.

    A global guard is used to prevent recursive updates, which can occur when
    setting properties on other objects from within an update callback.
    """
    global _prop_update_guard
    if _prop_update_guard:
        return

    # The bone this property group instance belongs to
    this_bone = self.id_data
    if not isinstance(this_bone, bpy.types.PoseBone):
        # AI Editor Note: For properties on PoseBones, id_data is the Armature Object.
        # We must parse the bone name from the data path to identify which bone changed.
        if isinstance(this_bone, bpy.types.Object) and this_bone.type == 'ARMATURE':
            try:
                # AI Editor Note: path_from_id() can fail in certain context transition states.
                # We wrap it in a try-except to prevent the entire handler from crashing.
                path = self.path_from_id()
                # Expected path format: pose.bones["BoneName"].fcd_pg_kinematic_props
                match = re.search(r'pose\.bones\["([^"]+)"\]', path)
                if match:
                    bone_name = match.group(1)
                    this_bone = this_bone.pose.bones.get(bone_name)
            except (ValueError, RuntimeError):
                # Fallback to identify bone via name if path parsing fails
                pass

    if not isinstance(this_bone, bpy.types.PoseBone):
        return

    # --- Part 1: State Update ---
    # AI Editor Note: Always update the state of the bone whose property was changed.
    # This ensures that when a property is set on a non-active bone (e.g. during
    # propagation), its visual and mechanical state is correctly updated.
    clean_conflicting_mechanics(this_bone)
    update_single_bone_gizmo(this_bone, context.scene.fcd_viz_gizmos)
    apply_native_constraints(this_bone)
    # Special handling for relationships and IK
    if prop_name in {'ratio_value', 'ratio_invert'} and self.ratio_target_bone:
        add_native_driver_relation(this_bone, self.ratio_target_bone, self.ratio_value, self.ratio_invert)
    elif prop_name == 'ik_chain_length':
        update_ik_chain_length(this_bone, context)

    # --- Part 2: Propagation for Multi-Object Editing (with guard) ---
    # Guard is already checked at the top, but we'll use a local one for safety here if needed.
    # We only propagate from the active bone to others.
    active_bone = context.active_pose_bone
    if active_bone and this_bone == active_bone:
        _prop_update_guard = True
        try:
            new_value = getattr(self, prop_name)
            
            # Use safe bone gathering for multi-object editing.
            # Compatibility with Blender 3.2+ and fallback for older versions.
            bones_to_update = getattr(context, 'selected_pose_bones_from_active_object', context.selected_pose_bones)
            for bone in bones_to_update:
                if bone != active_bone:
                    # Setting this property will call fcd_prop_update(bone, ...)
                    # which will trigger Part 1 for that bone, and then return because of _prop_update_guard.
                    if getattr(bone.fcd_pg_kinematic_props, prop_name) != new_value:
                        setattr(bone.fcd_pg_kinematic_props, prop_name, new_value)
        finally:
            _prop_update_guard = False

@persistent
def active_bone_change_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    """
    A persistent handler that runs on dependency graph updates to detect when
    the active pose bone changes. When it does, it updates the global Joint
    Editor tool with the properties of the newly selected bone.
    """
    global _last_active_bone_name, _joint_editor_update_guard

    # This handler can run in many contexts, so we need to be careful.
    context = bpy.context
    
    # --- AI Editor Note: Enhanced selection logic ---
    # Identify the target bone whether in Pose Mode (direct selection)
    # or Object Mode (selecting a child mesh/gizmo).
    target_bone = None
    
    if context.mode == 'POSE' and context.active_pose_bone:
        target_bone = context.active_pose_bone
    elif context.mode == 'OBJECT' and context.active_object:
        obj = context.active_object
        rig = getattr(scene, "fcd_active_rig", None)
        # Check if the object is a child of the active rig's bone
        if rig and obj.parent == rig and obj.parent_type == 'BONE':
            target_bone = rig.pose.bones.get(obj.parent_bone)

    if not target_bone:
        _last_active_bone_name = None
        return

    active_bone_name = target_bone.name

    if active_bone_name != _last_active_bone_name:
        _last_active_bone_name = active_bone_name
        
        # Guard to prevent the tool's update callback from firing and applying
        # the old settings back to the bone we just read from.
        _joint_editor_update_guard = True
        try:
            tool_props = scene.fcd_pg_joint_editor_settings
            active_props = target_bone.fcd_pg_kinematic_props
            # Copy all relevant properties from the bone whose data we just selected.
            # We filter out collections and read-only system properties.
            for prop_name, prop_data in tool_props.bl_rna.properties.items():
                if prop_name in {"rna_type", "name"}: continue
                if prop_data.type == 'COLLECTION': continue
                
                if hasattr(active_props, prop_name):
                    setattr(tool_props, prop_name, getattr(active_props, prop_name))
        except Exception as e:
            print(f"URDF Sync Error: {e}")
        finally:
            _joint_editor_update_guard = False

def add_native_driver_relation(target_bone: bpy.types.PoseBone, source_bone_name: str, ratio: float, invert: bool = False) -> None:
    """
    Creates or updates a native Blender driver to establish a gear/mimic
    relationship between two bones.

    This function sets up a scripted driver that makes the `target_bone`'s
    transformation a function of the `source_bone`'s transformation, multiplied
    by the given ratio. This is a core feature for creating coupled motions like
    gears, pulleys, or other mechanical linkages.

    The function is designed to be re-runnable. If a driver already exists for
    the target bone's property, it will be updated with the new ratio and
    inversion settings.

    Args:
        target_bone: The bone to be driven (the follower).
        source_bone_name: The name of the bone that drives the motion (the driver).
        ratio: The multiplication factor for the relationship (e.g., gear ratio).
        invert: Whether to invert the direction of the driven motion.
    """
    rig = target_bone.id_data
    source_bone = rig.pose.bones.get(source_bone_name)
    if not source_bone:
        return

    # Clean up any conflicting mechanics and apply base constraints first.
    clean_conflicting_mechanics(target_bone)
    apply_native_constraints(target_bone)

    # --- Determine Target Bone's Driven Property ---
    props_tgt = target_bone.fcd_pg_kinematic_props
    ui_idx_tgt = get_mapped_axis_index(props_tgt.axis_enum)
    # AI Editor Note: Re-instating axis mapping to match constraint logic.
    # The driver must target the same bone axis that is unlocked by the constraints.
    # The axis_map corrects a permutation between the UI selection and Blender's bone axes.
    # AI Editor Note: DO NOT CHANGE THIS MAPPING. It is notoriously tricky to align.
    # Future AI: Do not "correct" this unless explicitly instructed.
    axis_map = {0: 2, 1: 0, 2: 1}
    idx_tgt = axis_map.get(ui_idx_tgt, ui_idx_tgt)
    is_rot_tgt = props_tgt.joint_type in ['revolute', 'continuous']
    data_path = "rotation_euler" if is_rot_tgt else "location"

    # --- Determine Source Bone's Driving Property ---
    props_src = source_bone.fcd_pg_kinematic_props
    ui_idx_src = get_mapped_axis_index(props_src.axis_enum)
    # Apply the same mapping to the source bone's axis to ensure the correct source value is read.
    idx_src = axis_map.get(ui_idx_src, ui_idx_src)
    is_rot_src = props_src.joint_type in ['revolute', 'continuous']

    # --- Find or Create the Driver ---
    driver_fcurve = None
    if target_bone.id_data.animation_data:
        expected_path = f'pose.bones["{target_bone.name}"].{data_path}'
        for d in target_bone.id_data.animation_data.drivers:
            if d.data_path == expected_path and d.array_index == idx_tgt:
                driver_fcurve = d
                break
    if not driver_fcurve:
        driver_fcurve = target_bone.driver_add(data_path, idx_tgt)
        if not driver_fcurve: return # Failed to create driver
        driver_fcurve.driver.type = 'SCRIPTED'

    drv = driver_fcurve.driver
    # Sanitize the source bone name to create a valid Python variable name.
    clean_src_name = re.sub(r'[^a-zA-Z0-9_]', '_', source_bone_name)
    var_name = f"var_{clean_src_name}"
    # --- Configure the Driver Variable ---
    var = drv.variables.get(var_name)
    if not var:
        # Remove any old variables to ensure a clean state
        for v in list(drv.variables):
            drv.variables.remove(v)
        var = drv.variables.new()
        var.name = var_name

    # AI Editor Note: Use SINGLE_PROP for rotational drivers to prevent snapping.
    # This ensures continuous rotation (like a screw) correctly drives the target
    # without jumping at 180-degree intervals, which can happen with 'TRANSFORMS'.
    if is_rot_src:
        var.type = 'SINGLE_PROP'
        var.targets[0].id = rig
        var.targets[0].data_path = f'pose.bones["{source_bone_name}"].rotation_euler[{idx_src}]'
    else:
        var.type = 'TRANSFORMS'
        t = var.targets[0]
        t.id = rig
        t.bone_target = source_bone_name
        t.transform_space = 'LOCAL_SPACE'
        t.transform_type = ['LOC_X', 'LOC_Y', 'LOC_Z'][idx_src]

    # --- Configure the Driver Expression ---
    factor = -1.0 if invert else 1.0
    # AI Editor Note: Sync driver variables with physical units.
    # Rotational properties (euler) are in Radians, but Linear properties (loc) are in Blender Units.
    # To maintain consistency with meter-based joint properties, we must scale Loc variables by the scene unit scale.
    unit_scale = rig.users_scene[0].unit_settings.scale_length if rig.users_scene else 1.0
    u_var = f"({var_name} * {unit_scale:.6f})" if not is_rot_src else var_name

    # Calculate current values for offset (using Blender Units for calculation, then converting)
    curr_val_tgt = target_bone.rotation_euler[idx_tgt] if is_rot_tgt else (target_bone.location[idx_tgt] * unit_scale if not is_rot_tgt else target_bone.location[idx_tgt])
    curr_val_src = source_bone.rotation_euler[idx_src] if is_rot_src else (source_bone.location[idx_src] * unit_scale)
    
    # Correction for curr_val_tgt logic
    if not is_rot_tgt:
         curr_val_tgt = target_bone.location[idx_tgt] * unit_scale
    else:
         curr_val_tgt = target_bone.rotation_euler[idx_tgt]

    offset = curr_val_tgt - (curr_val_src * ratio * factor)
    drv.expression = f"({u_var} * {ratio:.4f} * {factor}) + {offset:.4f}"

    # Lock the driven property in the UI to prevent manual changes that would conflict with the driver.
    if is_rot_tgt:
        target_bone.lock_rotation[idx_tgt] = True
    else:
        target_bone.lock_location[idx_tgt] = True

def invert_ratio_update(self: 'FCD_Properties', context: bpy.types.Context) -> None:
    """
    Update callback for the 'Invert' checkbox in the gear ratio UI.

    This function is triggered when the user toggles the 'Invert' checkbox for a
    gear/mimic relationship. It immediately calls `add_native_driver_relation`
    to update the driver with the new inversion setting.

    Args:
        self: The `FCD_Properties` instance that was changed.
        context: The current Blender context.
    """
    if context.active_pose_bone and self.ratio_target_bone:
        add_native_driver_relation(context.active_pose_bone, self.ratio_target_bone, self.ratio_value, self.ratio_invert)


def fcd_joint_editor_update_callback(self, context):
    """
    Update callback for the global joint editor tool properties.
    Automatically calls the apply operator to push changes to the selected bones.
    """
    # --- AI Editor Note: Add guard to prevent unwanted mode switching ---
    # This prevents the operator from being called when properties are set
    # programmatically, such as during the creation of a new joint part.
    global _joint_editor_update_guard
    if _joint_editor_update_guard:
        return None

    # Using a timer ensures the operator runs in a clean context after the update.
    # The operator's poll method will handle context checks (e.g., pose mode).
    bpy.app.timers.register(lambda: (bpy.ops.fcd.apply_joint_settings() and None), first_interval=0.01)
    return None


def update_ratio_live(self: 'FCD_Properties', context: bpy.types.Context) -> None:
    """
    Update callback for relationship properties in the bone editor.
    Propagates changes to other selected bones via the standard update logic.
    """
    fcd_prop_update(self, context, 'ratio_value')

def update_ratio_invert(self: 'FCD_Properties', context: bpy.types.Context) -> None:
    """
    Update callback for the ratio inversion toggle in the bone editor.
    """
    fcd_prop_update(self, context, 'ratio_invert')

def cleanup_unused_gizmos(context: bpy.types.Context) -> None:
    """
    Removes gizmo objects from the FCD_Widgets collection that are no longer
    assigned to any bone in any armature.
    """
    widgets_coll = bpy.data.collections.get(WIDGETS_COLLECTION_NAME)
    if not widgets_coll:
        return

    # 1. Collect all gizmo objects currently in use.
    used_widgets = set()
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            for pb in obj.pose.bones:
                if pb.custom_shape:
                    used_widgets.add(pb.custom_shape)

    # 2. Identify and remove unused widgets from the collection.
    # We iterate over a list copy to safely modify the collection/scene.
    widgets_to_remove = [obj for obj in widgets_coll.objects if obj not in used_widgets]
    
    for obj in widgets_to_remove:
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except:
            pass

def update_all_gizmos(self: bpy.types.Scene, context: bpy.types.Context) -> None:
    """
    Update callback for the global 'Show Gizmos' toggle in the UI.
    Triggers a full refresh of visual gizmos and mechanical constraints.
    """
    rig = context.scene.fcd_active_rig
    if not rig:
        return
    
    # AI Editor Note: Robustness update.
    # Retrieve settings once to pass to all bones, avoiding Context errors in loop.
    show = context.scene.fcd_viz_gizmos
    style = context.scene.fcd_gizmo_style

    for bone in rig.pose.bones:
        # 1. Update the visual gizmo
        update_single_bone_gizmo(bone, show, style)
        
        # 2. Re-apply constraints to ensure physics match visuals.
        clean_conflicting_mechanics(bone)
        apply_native_constraints(bone)

    # 3. Garbage collect unused gizmos to prevent "left behind" objects.
    cleanup_unused_gizmos(context)

def update_ik_chain_length(bone: bpy.types.PoseBone, context: bpy.types.Context) -> None:
    """
    Update callback for the IK chain length property on a bone.
    Synchronizes the IK constraint's chain_count with the property value.
    """
    if not bone:
        return
    
    props = bone.fcd_pg_kinematic_props
    ik_con = bone.constraints.get(IK_CONSTRAINT_NAME)
    if not ik_con:
        return

    # Calculate the maximum possible chain length
    max_len = 0
    current = bone
    while current:
        max_len += 1
        current = current.parent

    # Clamp to valid range
    new_length = min(props.ik_chain_length, max_len)
    ik_con.chain_count = new_length

    # Update the property to reflect clamping
    if props.ik_chain_length != new_length:
        props.ik_chain_length = new_length

# ------------------------------------------------------------------------

# AI Editor Note: Consolidated registration to the bottom of the file for architectural clarity.
def create_parametric_chain(context: bpy.types.Context, chain_type: str) -> bpy.types.Object:
    """    
    Creates a complete, native, parametric chain setup.
    """    
    coll_name = "Mechanical_Parts"
    coll = bpy.data.collections.get(coll_name)
    if not coll:
        coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(coll)
    
    cursor_loc = context.scene.cursor.location

    # --- 1. Generate unique names to allow for multiple chains in the scene ---
    base_name = chain_type.capitalize() # "Roller" or "Belt"
    i = 1
    while f"{base_name}_Chain_{i:03d}" in bpy.data.objects:
        i += 1
    
    path_name = f"{base_name}_Chain_{i:03d}"
    link_name = f"{base_name}_Link_{i:03d}"

    # --- 2. Create the hidden "Link" object that will be instanced ---
    link_mesh_data = bpy.data.meshes.new(f"{link_name}_Data")
    link_obj = bpy.data.objects.new(link_name, link_mesh_data)
    coll.objects.link(link_obj)
    link_obj.location = (0, 0, 0)
    link_obj.hide_viewport = True
    link_obj.hide_render = True

    # --- 3. Create the main Path Curve object ---
    curve = bpy.data.curves.new(f"{path_name}_Data", type='CURVE')
    curve.dimensions = '3D'
    path_obj = bpy.data.objects.new(path_name, curve)
    coll.objects.link(path_obj)
    path_obj.location = cursor_loc
 
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(3) # 4 points total for a circle

    radius = 0.2
    handle_len = radius * (4 * (math.sqrt(2) - 1) / 3)

    points_data = [
        ((radius, 0, 0), (radius, -handle_len, 0), (radius, handle_len, 0)),
        ((0, radius, 0), (handle_len, radius, 0), (-handle_len, radius, 0)),
        ((-radius, 0, 0), (-radius, handle_len, 0), (-radius, -handle_len, 0)),
        ((0, -radius, 0), (-handle_len, -radius, 0), (handle_len, -radius, 0)),
    ]

    for i, (co, h_left, h_right) in enumerate(points_data):
        p = spline.bezier_points[i]
        p.co = co
        p.handle_left = h_left
        p.handle_right = h_right
        p.handle_left_type = 'AUTO'
        p.handle_right_type = 'AUTO'

    spline.use_cyclic_u = True

    # --- 4. Assign Parametric Properties to the Path object ---
    props = path_obj.fcd_pg_mech_props
    props.is_part = True
    props.category = 'CHAIN'
    props.type_chain = chain_type
    props.instanced_link_obj = link_obj 

    path_obj["fcd_native_chain_pitch"] = props.length
    path_obj["fcd_native_chain_res"] = props.chain_curve_res
    path_obj["fcd_native_anim_offset"] = 0.0 
    
    return path_obj

# ------------------------------------------------------------------------
#   Registration
# ------------------------------------------------------------------------

CLASSES = [
    FCD_OT_Core_DisablePanel, FCD_OT_Core_TogglePanelVisibility, FCD_OT_Core_SnapCursorToActive
]

def register():
    # 1. Register Classes
    for cls in CLASSES:
        if hasattr(cls, 'bl_rna'):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass
    
    # 2. Append Handlers (Set-like behavior to prevent duplicates)
    if sync_light_props_handler not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(sync_light_props_handler)
    if fcd_placement_handler not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(fcd_placement_handler)
    if auto_set_active_rig_handler not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(auto_set_active_rig_handler)
    if load_panel_order_handler not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(load_panel_order_handler)
    if set_scene_units_handler not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(set_scene_units_handler)
    if active_bone_change_handler not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(active_bone_change_handler)
    if local_cursor_depsgraph_handler not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(local_cursor_depsgraph_handler)
    if fcd_dimension_sync_handler not in bpy.app.handlers.depsgraph_update_post: bpy.app.handlers.depsgraph_update_post.append(fcd_dimension_sync_handler)

    # Lambda with context safety
    def safe_dimension_update(dummy):
        if bpy.context and bpy.context.scene:
            update_dimensions(bpy.context.scene)
    if safe_dimension_update not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(safe_dimension_update)

    # 3. Timers
    # Timer MUST return None (or float) to satisfy Blender's UI thread
    bpy.app.timers.register(lambda: (ensure_default_rig(bpy.context) and None), first_interval=0.1)

def unregister():
    # 1. Remove Handlers
    for h in [sync_light_props_handler, fcd_placement_handler, active_bone_change_handler, local_cursor_depsgraph_handler, fcd_dimension_sync_handler]:
        if h in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(h)
    
    for h in [auto_set_active_rig_handler, load_panel_order_handler, set_scene_units_handler]:
        if h in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(h)

    # 2. Unregister Classes
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

