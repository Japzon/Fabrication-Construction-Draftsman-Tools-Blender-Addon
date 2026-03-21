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
from .core import (
    ensure_default_rig,
    create_parametric_part_object,
    setup_and_update_material,
    get_unique_name,
    clean_conflicting_mechanics,
    update_single_bone_gizmo,
    apply_native_constraints,
    update_all_gizmos,
    update_ik_chain_length,
    create_parametric_chain,
    update_chain_driver_settings,
    apply_auto_smooth,
    setup_native_wrap_gn,
    get_all_children_objects,
    rig_parametric_joint,
    build_generative_robot,
    build_example_rover,
    build_example_arm,
    build_mobile_base_diff_drive,
    build_quadruped_spider,
    get_part_catalog_prompt,
)
from . import properties

#   PART 5: OPERATORS
# ------------------------------------------------------------------------

# --- ASSET LIBRARY SYSTEM OPERATORS ---
# --- ASSET LIBRARY SYSTEM OPERATORS ---
class URDF_OT_OpenAssetBrowser(bpy.types.Operator):
    """Opens the Asset Browser in a new window"""
    bl_idname = "urdf.open_asset_browser"
    bl_label = "Open Asset Browser"
    def execute(self, context):
        try:
            bpy.ops.wm.window_new()
            new_window = context.window_manager.windows[-1]
            area = new_window.screen.areas[0]
            area.type = 'FILE_BROWSER'
            area.ui_type = 'ASSETS'
        except Exception:
            pass
        return {'FINISHED'}

class URDF_OT_RegisterAssetCategory(bpy.types.Operator):
    """Creates a new folder and registers it as a Blender Asset Library"""
    bl_idname = "urdf.register_asset_category"
    bl_label = "Register Category"
    bl_description = "Creates a local folder and adds it to Blender's asset libraries list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.urdf_asset_props
        name = props.category_name
        
        # Default path in Blender User Data Asset folder
        base_path = os.path.join(bpy.utils.user_resource('DATAFILES'), "urdf_assets", name)
        
        try:
            if not os.path.exists(base_path):
                os.makedirs(base_path)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create directory: {e}")
            return {'CANCELLED'}
            
        # Register in Blender Preferences
        prefs = context.preferences
        filepaths = prefs.filepaths
        
        exists = False
        for lib in filepaths.asset_libraries:
            if lib.name == name:
                exists = True
                break
        
        if not exists:
            # Note: asset_library_add is a WM operator but we can call it.
            bpy.ops.preferences.asset_library_add(directory=base_path)
            # Find the newly added (last) and fix the name if needed (it might auto-name)
            new_lib = filepaths.asset_libraries[-1]
            new_lib.name = name
            self.report({'INFO'}, f"Registered Library: {name}")
        else:
            self.report({'WARNING'}, f"Category '{name}' is already registered.")
            
        return {'FINISHED'}

class URDF_OT_MarkAndUploadAsset(bpy.types.Operator):
    """Marks selected as assets for the active library"""
    bl_idname = "urdf.mark_and_upload_asset"
    bl_label = "Mark Selected as Asset"
    bl_description = "Tags the selected objects/collections as assets in the current file"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "No objects selected to mark as assets.")
            return {'CANCELLED'}
            
        for obj in context.selected_objects:
            if not obj.asset_data:
                obj.asset_mark()
                self.report({'INFO'}, f"Marked: {obj.name}")
            else:
                self.report({'INFO'}, f"Already marked: {obj.name}")
        
        props = context.scene.urdf_asset_props
        lib_name = props.target_library
        self.report({'INFO'}, f"Success. Save this file to your '{lib_name}' library to complete upload.")
        
        return {'FINISHED'}

class URDF_OT_ImportToAssetCategory(bpy.types.Operator, ImportHelper):
    """Imports an external file and prepares it as an asset"""
    bl_idname = "urdf.import_to_asset_category"
    bl_label = "Import to Active Category"
    bl_description = "Imports a 3D file and marks it as an asset automatically"
    
    filename_ext = ".obj;.fbx;.gltf;.glb;.stl"
    filter_glob: bpy.props.StringProperty(default="*.obj;*.fbx;*.gltf;*.glb;*.stl", options={'HIDDEN'})

    def execute(self, context):
        filepath = self.filepath
        ext = os.path.splitext(filepath)[1].lower()
        
        # Deselect to track imported
        bpy.ops.object.select_all(action='DESELECT')
        
        try:
            if ext == '.obj':
                bpy.ops.wm.obj_import(filepath=filepath)
            elif ext == '.fbx':
                bpy.ops.import_scene.fbx(filepath=filepath)
            elif ext in ['.gltf', '.glb']:
                bpy.ops.import_scene.gltf(filepath=filepath)
            elif ext == '.stl':
                bpy.ops.wm.stl_import(filepath=filepath)
            else:
                self.report({'ERROR'}, f"Unsupported format: {ext}")
                return {'CANCELLED'}
                
            # Mark imported as asset
            for obj in context.selected_objects:
                obj.asset_mark()
                
            self.report({'INFO'}, f"Imported and marked {os.path.basename(filepath)}")
        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {e}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

# --- MAIN OPERATORS ---
class OPS_OT_Execute_AI_Prompt(bpy.types.Operator):
    """
    Executes the AI generation process based on the user's prompt.
    
    AI Editor Note:
    This is the entry point for the AI generation logic. The `execute` method
    is responsible for interpreting the user's intent and triggering the
    appropriate generative function.

    For this version, it uses simple keyword matching on the prompt to decide
    whether to call the `build_example_rover` function. This demonstrates a
    basic but functional dispatch mechanism.

    In a future, more advanced implementation, this operator would be responsible for:
    1.  Securely retrieving the API key.
    2.  Packaging the prompt and sending it to a remote LLM service.
    3.  Receiving a structured plan (e.g., a JSON list of Python commands or
        operator calls) from the LLM.
    4.  Safely executing that plan.
    """
    bl_idname = "urdf.execute_ai_prompt"
    bl_label = "Generate Robot with AI"
    bl_description = "Takes the prompt and sends it to the AI to generate the robot"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # The operator can only run if there is a prompt.
        ai_props = context.scene.urdf_ai_props
        return ai_props and ai_props.api_prompt != ""

    def execute(self, context: bpy.types.Context) -> Set[str]:
        ai_props = context.scene.urdf_ai_props
        prompt = ai_props.api_prompt.lower()

        # AI Editor Note: Add scaling factor from the generation cage
        scale_factor = 1.0
        if context.scene.urdf_use_generation_cage:
            scale_factor = context.scene.urdf_generation_cage_size

        # --- AI Dispatch Logic (Local vs API) ---
        if ai_props.ai_source == 'FREE':
            # Use the new local procedural generator
            try:
                self.report({'INFO'}, f"Interpreting prompt: '{prompt}'...")
                build_generative_robot(context, prompt, scale_factor=scale_factor)
                self.report({'INFO'}, "Robot generation complete.")
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to generate robot: {e}")
                import traceback
                traceback.print_exc()
                return {'CANCELLED'}
        
        elif ai_props.ai_source == 'API':
            # Placeholder for future API integration
            # AI Editor Note: Construct the prompt that WOULD be sent to the API.
            system_prompt = get_part_catalog_prompt()
            print(f"--- CLOUD AI PROMPT ---\n{system_prompt}\nUser Prompt: {prompt}\n-----------------------")
            self.report({'INFO'}, "Cloud API request simulated (see Console). Please use 'Free (Local)' mode for now.")
            return {'CANCELLED'}
        else:
            return {'CANCELLED'}

class URDF_OT_Generate_Preset(bpy.types.Operator):
    """Generates a pre-defined robot template without using AI"""
    bl_idname = "urdf.generate_preset"
    bl_label = "Generate Template"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        template = context.scene.urdf_ai_props.robot_template
        
        # AI Editor Note: Add scaling factor from the generation cage
        scale_factor = 1.0
        if context.scene.urdf_use_generation_cage:
            # Use the smallest dimension of the cage as a uniform scale factor
            scale_factor = context.scene.urdf_generation_cage_size
        
        try:
            if template == 'ROVER':
                build_example_rover(context, scale_factor=scale_factor)
            elif template == 'ARM':
                build_example_arm(context, scale_factor=scale_factor)
            elif template == 'MOBILE_BASE':
                build_mobile_base_diff_drive(context, scale_factor=scale_factor)
            elif template == 'QUADRUPED':
                build_quadruped_spider(context, scale_factor=scale_factor)
            
            self.report({'INFO'}, f"Generated template: {template}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to generate template: {e}")
            return {'CANCELLED'}

class URDF_OT_SetJointType(bpy.types.Operator):
    """Sets the joint type for all selected pose bones and updates their state"""
    bl_idname = "urdf.set_joint_type"
    bl_label = "Set Joint Type"
    bl_description = "Sets the joint type for all selected pose bones and updates their state"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.EnumProperty(
        items=[
            ('none', "None", "No joint, bone is a free-floating link"),
            ('base', "Base", "A root joint that can be moved and rotated freely"),
            ('fixed', "Fixed", "A rigid connection with no movement"),
            ('revolute', "Revolute", "A hinge-like joint that rotates around a single axis"),
            ('continuous', "Continuous", "A revolute joint with no limits"),
            ('prismatic', "Linear", "A sliding joint that moves along a single axis")
        ],
        name="Joint Type"
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # In Blender 3.2+, use context.selected_pose_bones_from_active_object
        if hasattr(context, 'selected_pose_bones_from_active_object'):
            return context.mode == 'POSE' and len(context.selected_pose_bones_from_active_object) > 0
        return context.mode == 'POSE' and len(context.selected_pose_bones) > 0

    def execute(self, context: bpy.types.Context) -> Set[str]:
        """
        Executes the operator, applying the joint type and all necessary state
        updates to every selected pose bone.
        """
        bones_to_update = []
        if hasattr(context, 'selected_pose_bones_from_active_object'):
            bones_to_update = context.selected_pose_bones_from_active_object
        else:
            # Fallback for older Blender versions
            bones_to_update = context.selected_pose_bones

        for pbone in bones_to_update:
            # 1. Set the property value directly.
            pbone.urdf_props.joint_type = self.type
            
            # 2. Manually call all state update functions for each bone.
            # This ensures the changes are immediately reflected in the viewport
            # and the rig's behavior, bypassing the need for an update callback.
            clean_conflicting_mechanics(pbone)
            update_single_bone_gizmo(pbone, context.scene.urdf_viz_gizmos)
            apply_native_constraints(pbone)
        
        self.report({'INFO'}, f"Set joint type to '{self.type}' for {len(bones_to_update)} bones.")
        return {'FINISHED'}


class OPS_OT_CalculateCenterOfMass(bpy.types.Operator):
    """Calculates the center of mass for the link's visual meshes"""
    bl_idname = "urdf.calculate_center_of_mass"
    bl_label = "Calculate from Visuals"
    bl_description = "Calculate the center of mass from the link's visual meshes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode == 'POSE':
            bones = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
            return any(bone and len(get_all_children_objects(bone, context)) > 0 for bone in bones)
        return False

    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for pbone in bones_to_process:
            if not pbone: continue
                
            child_meshes = get_all_children_objects(pbone, context)
            if not child_meshes:
                continue

            # Calculate the weighted average of the centers of volume
            total_volume = 0
            weighted_center = mathutils.Vector((0, 0, 0))

            for obj in child_meshes:
                # Ensure the object has its transformations evaluated
                depsgraph = context.evaluated_depsgraph_get()
                eval_obj = obj.evaluated_get(depsgraph)
                
                # Create a temporary mesh with all modifiers applied
                temp_mesh = bpy.data.meshes.new_from_object(eval_obj)
                if not temp_mesh.polygons:
                    bpy.data.meshes.remove(temp_mesh)
                    continue

                bm = bmesh.new()
                bm.from_mesh(temp_mesh)
                
                volume = bm.calc_volume()
                # Manual calculation of bounding box center (replaces missing bm.calc_center_bounds)
                if bm.verts:
                    min_v = mathutils.Vector((min(v.co.x for v in bm.verts), min(v.co.y for v in bm.verts), min(v.co.z for v in bm.verts)))
                    max_v = mathutils.Vector((max(v.co.x for v in bm.verts), max(v.co.y for v in bm.verts), max(v.co.z for v in bm.verts)))
                    center_local = (min_v + max_v) / 2
                else:
                    center_local = mathutils.Vector((0, 0, 0))
                
                weighted_center += (obj.matrix_world @ center_local) * volume
                total_volume += volume
                
                bm.free()
                bpy.data.meshes.remove(temp_mesh)

            if total_volume > 0:
                avg_center_world = weighted_center / total_volume
                link_frame_matrix = pbone.id_data.matrix_world @ pbone.matrix
                com_local = link_frame_matrix.inverted() @ avg_center_world
                pbone.urdf_props.inertial.center_of_mass = com_local
                count += 1
                
        self.report({'INFO'}, f"Calculated center of mass for {count} bone(s).")
        return {'FINISHED'}


class OPS_OT_CalculateInertia(bpy.types.Operator):
    """
    Calculates and populates the inertia tensor fields for a link based on its
    mass, dimensions, and collision shape.
    """
    bl_idname = "urdf.calculate_inertia"
    bl_label = "Calculate Inertia from Shape"
    bl_description = "Calculate the inertia tensor based on the mass and collision shape"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        obj = context.active_object
        
        count = 0
        if context.mode == 'POSE':
            for pbone in bones_to_process:
                if not pbone: continue
                props = pbone.urdf_props
                
                # For bones, we need to find the meshes parented to it to get dimensions
                child_meshes = get_all_children_objects(pbone, context)
                if not child_meshes: continue
                
                # Calculate bounding box of all children meshes in bone local space
                link_frame_matrix = pbone.id_data.matrix_world @ pbone.matrix
                inv_link_matrix = link_frame_matrix.inverted()
                
                min_v = mathutils.Vector((float('inf'), float('inf'), float('inf')))
                max_v = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
                
                for mesh_obj in child_meshes:
                    for v in mesh_obj.bound_box:
                        v_world = mesh_obj.matrix_world @ mathutils.Vector(v)
                        v_local = inv_link_matrix @ v_world
                        for i in range(3):
                            min_v[i] = min(min_v[i], v_local[i])
                            max_v[i] = max(max_v[i], v_local[i])
                
                dims = max_v - min_v
                self._calculate_for_props(props, dims)
                count += 1
        elif obj and obj.urdf_mech_props.is_part:
            self._calculate_for_props(obj.urdf_mech_props, obj.dimensions)
            count += 1
            
        self.report({'INFO'}, f"Calculated inertia for {count} item(s).")
        return {'FINISHED'}

    def _calculate_for_props(self, props, dims):
        mass = props.inertial.mass
        shape = props.collision.shape
        if shape == 'BOX':
            ixx = (1/12) * mass * (dims.y**2 + dims.z**2)
            iyy = (1/12) * mass * (dims.x**2 + dims.z**2)
            izz = (1/12) * mass * (dims.x**2 + dims.y**2)
            props.inertial.ixx = ixx
            props.inertial.iyy = iyy
            props.inertial.izz = izz
        elif shape == 'CYLINDER':
            radius = (dims.x + dims.y) / 4
            height = dims.z
            ixx = (1/12) * mass * (3 * radius**2 + height**2)
            iyy = (1/12) * mass * (3 * radius**2 + height**2)
            izz = (1/2) * mass * radius**2
            props.inertial.ixx = ixx
            props.inertial.iyy = iyy
            props.inertial.izz = izz
        elif shape == 'SPHERE':
            radius = max(dims.x, dims.y, dims.z) / 2
            val = (2/5) * mass * radius**2
            props.inertial.ixx = val
            props.inertial.iyy = val
            props.inertial.izz = val

class OPS_OT_BakeMesh(bpy.types.Operator):
    """
    Applies all modifiers and converts a parametric object to a plain static mesh,
    permanently removing its parametric controls and helper objects.
    """
    bl_idname = "urdf.bake_mesh"
    bl_label = "Bake to Static Mesh"
    bl_description = "Convert the parametric part to a static mesh, applying all modifiers and removing parametric controls"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return obj and obj.type in {'MESH', 'CURVE'} and hasattr(obj, "urdf_mech_props") and obj.urdf_mech_props.is_part

    def execute(self, context: bpy.types.Context) -> Set[str]:
        """
        Executes the baking process.

        This operator uses a robust, multi-step process to ensure a clean conversion:
        1.  A temporary duplicate of the object is created.
        2.  Blender's native `convert` operator is used on the duplicate. This is the
            most reliable way to apply all modifiers, including Geometry Nodes that
            generate instances (like chains).
        3.  A new, final baked object is created from the resulting mesh data.
        4.  All original parametric objects and their specific helpers (cutters,
            empties, link meshes) are identified by inspecting properties, not by
            relying on fragile naming conventions.
        5.  The original objects and their now-unused data-blocks are deleted.
        6.  The new baked object is selected for a seamless user experience.
        """
        obj_to_bake = context.active_object
        original_obj_name = obj_to_bake.name

        # --- 1. Ensure Object Mode for safe operations ---
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # --- 2. Create the final mesh data using the robust convert operator ---
        # This is more reliable than `new_from_object` for complex GN setups.
        # AI Editor Note: Use manual deselection to avoid operator context errors.
        for o in context.view_layer.objects:
            o.select_set(False)
        obj_to_bake.select_set(True)
        context.view_layer.objects.active = obj_to_bake
        # Duplicate the object to work on a temporary copy.
        bpy.ops.object.duplicate(linked=False)
        temp_baked_obj = context.active_object

        try:
            # Convert the duplicate to a mesh, applying all modifiers.
            bpy.ops.object.convert(target='MESH')
            # Apply transforms to "lock in" the geometry.
            # AI Editor Note: Only apply scale to ensure URDF compatibility (uniform scale).
            # We keep location and rotation on the object to preserve the pivot point,
            # preventing the object from "jumping" to the world origin.
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            baked_mesh_data = temp_baked_obj.data.copy()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to convert object to mesh: {e}")
            # Clean up the temporary duplicate on failure.
            if temp_baked_obj:
                bpy.data.objects.remove(temp_baked_obj, do_unlink=True)
            return {'CANCELLED'}
        finally:
            # Always clean up the temporary object.
            if temp_baked_obj and temp_baked_obj.name in bpy.data.objects:
                 bpy.data.objects.remove(temp_baked_obj, do_unlink=True)


        # --- 3. Create the new, final baked object ---
        baked_obj_name = get_unique_name(f"{original_obj_name}_Baked")
        baked_obj = bpy.data.objects.new(baked_obj_name, baked_mesh_data)
        
        # Copy location and rotation from original, but reset scale to 1.0
        # because we just baked the scale into the mesh.
        loc, rot, _ = obj_to_bake.matrix_world.decompose()
        baked_obj.matrix_world = mathutils.Matrix.LocRotScale(loc, rot, mathutils.Vector((1.0, 1.0, 1.0)))
        context.collection.objects.link(baked_obj)

        # --- 4. Collect all original parametric objects and helpers for deletion ---
        objects_to_delete = {obj_to_bake}
        props = obj_to_bake.urdf_mech_props
        
        # --- AI Editor Note: Handle Basic Joint Stator Baking ---
        # If this is a basic joint, we must also bake the stator object.
        # We do this by recursively calling the bake operator on the stator,
        # or manually converting it here. Manual conversion is safer to avoid context switching issues.
        if props.category == 'BASIC_JOINT' and props.joint_stator_obj:
            stator = props.joint_stator_obj
            # Unlink the stator from the properties so it doesn't get deleted as a helper
            props.joint_stator_obj = None
            
            # Convert Stator to static mesh
            # We can simply clear its 'is_part' flag, as it's already a mesh object.
            # But to be consistent with 'Bake', we should apply any modifiers if they existed (AutoSmooth).
            # Since we are in a script, we can just apply the modifiers.
            # For now, just marking it as not a part is sufficient to "bake" it in the UI sense.
            stator.urdf_mech_props.is_part = False

        if props.category == 'BASIC_JOINT' and props.joint_screw_obj:
            screw = props.joint_screw_obj
            props.joint_screw_obj = None
            screw.urdf_mech_props.is_part = False

        if props.category == 'BASIC_JOINT' and props.joint_pin_obj:
            pin = props.joint_pin_obj
            props.joint_pin_obj = None
            pin.urdf_mech_props.is_part = False

        # Find boolean cutters by inspecting modifiers.
        for mod in obj_to_bake.modifiers:
            if mod.type == 'BOOLEAN' and mod.object:
                objects_to_delete.add(mod.object)

        # Find helpers stored in pointer properties for specific part types.
        if props.category == 'SPRING':
            if props.spring_start_obj: objects_to_delete.add(props.spring_start_obj)
            if props.spring_end_obj: objects_to_delete.add(props.spring_end_obj)
        elif props.category == 'CHAIN':
            if props.instanced_link_obj: objects_to_delete.add(props.instanced_link_obj)
            if props.chain_driver: objects_to_delete.add(props.chain_driver)
            if props.chain_follower_proxy: objects_to_delete.add(props.chain_follower_proxy)

        # --- 5. Delete the original objects and their data-blocks ---
        for item in objects_to_delete:
            if item and item.name in bpy.data.objects:
                data = item.data
                is_data_user = isinstance(data, (bpy.types.Mesh, bpy.types.Curve))
                bpy.data.objects.remove(item, do_unlink=True)
                # Clean up orphan data-blocks to keep the .blend file clean.
                if is_data_user and data and data.users == 0:
                    if isinstance(data, bpy.types.Mesh):
                        bpy.data.meshes.remove(data)
                    elif isinstance(data, bpy.types.Curve):
                        bpy.data.curves.remove(data)

        # Mark the new object as no longer being a parametric part to hide the UI.
        baked_obj.urdf_mech_props.is_part = False

        # --- 6. Select the new baked object for a good user experience ---
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = baked_obj
        baked_obj.select_set(True)

        self.report({'INFO'}, f"Baked '{original_obj_name}' to static mesh: '{baked_obj.name}'")
        return {'FINISHED'}


class URDF_OT_ReadJointSettings(bpy.types.Operator):
    """Reads the properties from the active bone into the global Joint Editor tool."""
    bl_idname = "urdf.read_joint_settings"
    bl_label = "Read From Active"
    bl_description = "Load settings from the currently active bone"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode == 'POSE':
            return context.active_pose_bone is not None
        if context.mode == 'OBJECT':
            obj = context.active_object
            rig = context.scene.urdf_active_rig
            return obj and rig and obj.parent == rig and obj.parent_type == 'BONE'
        return False

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # AI Editor Note: Support reading from the parent bone of a selected mesh in Object Mode.
        if context.mode == 'OBJECT':
            bpy.ops.urdf.enter_pose_mode()
            
        tool_props = context.scene.urdf_joint_editor_settings
        active_props = context.active_pose_bone.urdf_props

        tool_props.joint_type = active_props.joint_type
        tool_props.axis_enum = active_props.axis_enum
        tool_props.joint_radius = active_props.joint_radius
        tool_props.gizmo_radius = active_props.gizmo_radius
        tool_props.lower_limit = active_props.lower_limit
        tool_props.upper_limit = active_props.upper_limit
        tool_props.ik_chain_length = active_props.ik_chain_length
        
        self.report({'INFO'}, f"Read settings from '{context.active_pose_bone.name}'")
        return {'FINISHED'}


class URDF_OT_ApplyJointSettings(bpy.types.Operator):
    """Applies the properties from the global Joint Editor tool to all selected bones."""
    bl_idname = "urdf.apply_joint_settings"
    bl_label = "Apply to Selected"
    bl_description = "Apply the settings below to all selected bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        # AI Editor Note: Relaxed poll to allow execution in Object Mode if a valid bone-parented mesh is selected.
        if context.mode == 'POSE':
            if hasattr(context, 'selected_pose_bones_from_active_object'):
                return len(context.selected_pose_bones_from_active_object) > 0
            return len(context.selected_pose_bones) > 0
        if context.mode == 'OBJECT':
            rig = context.scene.urdf_active_rig
            if not rig:
                return False
            if rig in context.selected_objects:
                return True
            # Check if any selected object (or its hierarchical descendants/ancestors) is connected to a rig bone
            for obj in context.selected_objects:
                curr = obj
                while curr:
                    if curr.parent == rig and curr.parent_type == 'BONE':
                        return True
                    curr = curr.parent
                # Also check descendants
                def has_bone_connection(o):
                    if o.parent == rig and o.parent_type == 'BONE':
                        return True
                    for child in o.children:
                        if has_bone_connection(child):
                            return True
                    return False
                if has_bone_connection(obj):
                    return True
                    
            if core._last_active_bone_name and rig.pose.bones.get(core._last_active_bone_name):
                return True
        return False

    def execute(self, context: bpy.types.Context) -> Set[str]:
        tool_props = context.scene.urdf_joint_editor_settings
        
        bones_to_update = []
        
        # Determine the active rig for context
        rig = context.scene.urdf_active_rig
        if not rig:
            # Fallback to active object or selected armature
            if context.active_object and context.active_object.type == 'ARMATURE':
                rig = context.active_object
            else:
                for obj in context.selected_objects:
                    if obj.type == 'ARMATURE':
                        rig = obj; break
                    if obj.parent and obj.parent.type == 'ARMATURE':
                        rig = obj.parent; break

        if context.mode == 'POSE':
            if hasattr(context, 'selected_pose_bones_from_active_object') and context.selected_pose_bones_from_active_object:
                bones_to_update = list(context.selected_pose_bones_from_active_object)
            elif rig and rig.type == 'ARMATURE':
                # AI Editor Note: Robust fallback for timers where context.selected_pose_bones may be empty.
                bones_to_update = [b for b in rig.pose.bones if b.bone.select]
                # If still empty, fall back to active bone
                if not bones_to_update and rig.pose.bones.active:
                    bones_to_update = [rig.pose.bones.active]
        elif context.mode == 'OBJECT':
            if rig:
                for obj in context.selected_objects:
                    if obj == rig: continue
                    # Find all bones associated with this selection hierarchy
                    def find_bones_in_hierarchy(o):
                        # 1. Check if this object or any parent is bound to a bone
                        curr = o
                        while curr:
                            if curr.parent == rig and curr.parent_type == 'BONE' and curr.parent_bone:
                                pbone = rig.pose.bones.get(curr.parent_bone)
                                if pbone and pbone not in bones_to_update:
                                    bones_to_update.append(pbone)
                                break # Found the root attachment for this branch
                            curr = curr.parent
                        
                        # 2. Check all descendants for bone attachments
                        for child in o.children:
                            find_bones_in_hierarchy(child)
                            
                    find_bones_in_hierarchy(obj)
                
                # If no bones found from selection, fallback to active bone if rig is active
                if not bones_to_update and rig == context.active_object and rig.pose.bones.active:
                    bones_to_update = [rig.pose.bones.active]
                
                # Ultimate fallback to tracked active bone from UI interactions
                if not bones_to_update and core._last_active_bone_name:
                    pbone = rig.pose.bones.get(core._last_active_bone_name)
                    if pbone:
                        bones_to_update = [pbone]
        
        if not bones_to_update:
            return {'CANCELLED'}

        # AI Editor Note: Use the property update guard to prevent redundant logic 
        # and recursion while we set multiple properties per bone.
        old_guard = core._prop_update_guard
        core._prop_update_guard = True

        try:
            for bone in bones_to_update:
                props = bone.urdf_props
                props.joint_type = tool_props.joint_type
                props.axis_enum = tool_props.axis_enum
                props.joint_radius = tool_props.joint_radius
                props.gizmo_radius = tool_props.gizmo_radius
                props.lower_limit = tool_props.lower_limit
                props.upper_limit = tool_props.upper_limit
                
                if props.ik_chain_length != tool_props.ik_chain_length:
                    props.ik_chain_length = tool_props.ik_chain_length

                # AI Editor Note: Manually trigger state updates ONCE per bone after setting all properties.
                clean_conflicting_mechanics(bone)
                update_single_bone_gizmo(bone, context.scene.urdf_viz_gizmos)
                apply_native_constraints(bone)
                update_ik_chain_length(props, context)
        finally:
            core._prop_update_guard = old_guard
            
        self.report({'INFO'}, f"Applied joint settings to {len(bones_to_update)} bones")
        # AI Editor Note: Removed auto-switch to Pose Mode to prevent "getting stuck" 
        # when editing from Object Mode. Users should stay in their current mode.
        return {'FINISHED'}


class OPS_OT_SetupIK(bpy.types.Operator):
    """
    Creates a standard Inverse Kinematics (IK) setup for the active bone,
    including a target bone and a pole target bone.
    """
    bl_idname = "urdf.setup_ik"
    bl_label = "Setup IK Chain"
    bl_description = "Create an IK chain from the active bone up to its root, including a target and pole bone"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'POSE' and context.active_pose_bone

    def execute(self, context: bpy.types.Context) -> Set[str]:
        rig = context.object
        ik_bone = context.active_pose_bone

        # --- Cleanup old IK constraint to make the operator re-runnable ---
        for c in list(ik_bone.constraints):
            if c.name == IK_CONSTRAINT_NAME:
                ik_bone.constraints.remove(c)
        
        # 1. Traverse up the hierarchy to find the chain of parent bones.
        chain = []
        current_bone = ik_bone
        while current_bone:
            chain.append(current_bone)
            if len(chain) >= 255:  # Blender's IK chain limit
                break
            current_bone = current_bone.parent
        
        if len(chain) < 1:
            self.report({'WARNING'}, "Could not determine bone chain.")
            return {'CANCELLED'}
            
        chain_length = len(chain)
        
        # 2. Switch to Edit Mode to create the new IK controller bones.
        bpy.ops.object.mode_set(mode='EDIT')
        
        edit_bones = rig.data.edit_bones
        
        # Get the edit bone versions of the chain, reversed (from tip to root).
        chain_edit_bones = [edit_bones.get(b.name) for b in chain]
        
        # 3. Create the IK Target Bone at the tip of the chain.
        ik_target_name = f"IK_Target_{ik_bone.name}"
        ik_target_eb = edit_bones.new(ik_target_name)
        ik_target_eb.head = chain_edit_bones[0].tail
        ik_target_eb.tail = ik_target_eb.head + (chain_edit_bones[0].tail - chain_edit_bones[0].head).normalized() * 0.2
        ik_target_eb.parent = None  # Un-parent it from the chain.
        
        # 4. Create the Pole Target Bone for controlling the "elbow" or "knee".
        pole_target_name = f"IK_Pole_{ik_bone.name}"
        pole_target_eb = None
        if chain_length > 1:
            pole_target_eb = edit_bones.new(pole_target_name)
            
            # Calculate a good default position for the pole target.
            root_pos = chain_edit_bones[-1].head
            tip_pos = chain_edit_bones[0].tail
            elbow_pos = chain_edit_bones[0].head
            
            v_root_tip = tip_pos - root_pos
            v_root_elbow = elbow_pos - root_pos
            v_proj = v_root_elbow.project(v_root_tip)
            v_pole = v_root_elbow - v_proj
            
            pole_distance = v_root_tip.length
            if v_pole.length < 0.001:
                # If the arm is straight, default to a pole vector along the world Z-axis.
                v_pole = mathutils.Vector((0, 0, 1.0))
            
            pole_target_eb.head = elbow_pos + v_pole.normalized() * pole_distance
            pole_target_eb.tail = pole_target_eb.head + mathutils.Vector((0, 0, 0.2))
            pole_target_eb.parent = None

        # 5. Switch back to Pose Mode to create the constraint.
        bpy.ops.object.mode_set(mode='POSE')
        
        ik_con = ik_bone.constraints.new('IK')
        ik_con.name = IK_CONSTRAINT_NAME
        ik_con.target = rig
        ik_con.subtarget = ik_target_name
        ik_con.chain_count = chain_length
        # ik_con.use_ik_limit = True # REMOVED: Attribute does not exist on KinematicConstraint
        
        if pole_target_eb:
            ik_con.pole_target = rig
            ik_con.pole_subtarget = pole_target_name

        # --- UX Improvement: Auto-select the target and activate the move tool ---
        bpy.ops.pose.select_all(action='DESELECT')
        target_pose_bone = rig.pose.bones.get(ik_target_name)
        if target_pose_bone:
            target_pose_bone.bone.select = True
            rig.data.bones.active = target_pose_bone.bone
            bpy.ops.wm.tool_set_by_id(name="builtin.move")

        self.report({'INFO'}, f"Created IK chain of length {chain_length} on '{ik_bone.name}'")
        return {'FINISHED'}

class OPS_OT_SetOriginToCursor(bpy.types.Operator):
    """Moves the origin of the selected object(s) to the 3D cursor"""
    bl_idname = "urdf.set_origin_to_cursor"
    bl_label = "Set Origin to Cursor"
    bl_description = "Moves the origin of the selected object(s) to the 3D cursor"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None and len(context.selected_objects) > 0

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # AI Editor Note: This operator is a simple wrapper around Blender's native
        # 'origin_set' function. To ensure it works from any mode (Pose, Edit, etc.),
        # we temporarily switch to Object Mode, perform the operation, and then restore the mode.
        # This aligns with the addon's philosophy of using native features while improving UX.
        
        original_mode = context.mode

        # --- AI Editor Note: Map specific edit modes (e.g., 'EDIT_MESH') to the generic 'EDIT' ---
        # The bpy.ops.object.mode_set() operator expects generic mode names like 'EDIT', not 'EDIT_MESH'.
        # This mapping prevents a TypeError when trying to restore the original mode.
        mode_to_restore = original_mode
        if original_mode.startswith('EDIT_'):
            mode_to_restore = 'EDIT'
        
        try:
            # Switch to Object Mode if necessary, as origin_set requires it.
            if original_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            
            # AI Editor Note: Support sub-selection/hierarchies.
            # Blender's origin_set works on selected objects. We must select descendants if the user expects them to be affected.
            for obj in context.selected_objects:
                def select_descendants(o):
                    for child in o.children:
                        child.select_set(True)
                        select_descendants(child)
                select_descendants(obj)

            bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
            
            # Restore the original mode if possible.
            if original_mode != 'OBJECT':
                try:
                    # AI Editor Note: Use the mapped mode name for restoration.
                    bpy.ops.object.mode_set(mode=mode_to_restore)
                except RuntimeError:
                    # If mode restoration fails (e.g. invalid context), stay in Object Mode.
                    pass

            self.report({'INFO'}, f"Moved origin of {len(context.selected_objects)} object(s) to cursor.")
        except RuntimeError as e:
            self.report({'ERROR'}, f"Could not set origin. Error: {e}")
            # Attempt to restore mode even on error to avoid leaving user in unexpected state.
            if context.mode != original_mode:
                try:
                    # AI Editor Note: Use the mapped mode name for restoration on error.
                    bpy.ops.object.mode_set(mode=mode_to_restore)
                except:
                    pass
            return {'CANCELLED'}
        return {'FINISHED'}


# ------------------------------------------------------------------------
#   SECTION: MATERIAL & TEXTURING SYSTEM (REWRITTEN)
# ------------------------------------------------------------------------

def update_material_merge_trigger(self, context):
    """Trigger a re-merge when layer settings change."""
    # Use a timer to avoid context issues during property updates
    if context.active_object:
        bpy.app.timers.register(lambda: bpy.ops.urdf.material_merge() or None, first_interval=0.01)

class URDF_OT_Material_AddSmart(bpy.types.Operator):
    """Add a new material slot with a pre-configured smart material preset"""
    bl_idname = "urdf.material_add_smart"
    bl_label = "Add Smart Material"
    bl_description = "Adds a new material layer with a specific preset configuration"
    bl_options = {'REGISTER', 'UNDO'}
    
    mat_type: bpy.props.EnumProperty(
        name="Material Type",
        items=[
            ('PLASTIC', "Plastic", "Standard dielectric material"),
            ('METAL', "Metal", "Conductive metallic material"),
            ('RUBBER', "Rubber", "High roughness, dark material"),
            ('EMISSIVE', "Emissive", "Glowing light source"),
            ('GLASS', "Glass", "Transparent material"),
            ('CARBON', "Carbon Fiber", "Procedural carbon fiber pattern"),
            ('PRINTED', "3D Printed", "Plastic with layer lines"),
            ('ALUMINUM', "Brushed Aluminum", "Anisotropic metallic"),
        ]
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Active object must be a mesh.")
            return {'CANCELLED'}
        
        # 1. Create Slot
        bpy.ops.object.material_slot_add()
        slot = obj.material_slots[obj.active_material_index]
        
        # 2. Create Material
        mat = bpy.data.materials.new(name=f"{self.mat_type.capitalize()}_{obj.name}")
        mat.use_nodes = True
        slot.material = mat
        
        # 3. Configure Nodes
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        
        if not bsdf:
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            output = nodes.get("Material Output") or nodes.new('ShaderNodeOutputMaterial')
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # Apply Preset Logic
        if self.mat_type == 'PLASTIC':
            bsdf.inputs['Roughness'].default_value = 0.5
            bsdf.inputs['Metallic'].default_value = 0.0
        elif self.mat_type == 'METAL':
            bsdf.inputs['Roughness'].default_value = 0.2
            bsdf.inputs['Metallic'].default_value = 1.0
            bsdf.inputs['Base Color'].default_value = (0.8, 0.8, 0.8, 1.0)
        elif self.mat_type == 'RUBBER':
            bsdf.inputs['Base Color'].default_value = (0.1, 0.1, 0.1, 1.0)
            bsdf.inputs['Roughness'].default_value = 0.9
            bsdf.inputs['Metallic'].default_value = 0.0
        elif self.mat_type == 'EMISSIVE':
            bsdf.inputs['Emission Strength'].default_value = 5.0
        elif self.mat_type == 'GLASS':
            bsdf.inputs['Transmission Weight'].default_value = 1.0
            bsdf.inputs['Roughness'].default_value = 0.0
        elif self.mat_type == 'CARBON':
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-700, 0)
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-500, 0)
            links.new(coord.outputs['UV'], mapping.inputs['Vector'])
            
            tex = nodes.new('ShaderNodeTexBrick')
            tex.location = (-300, 0)
            links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            
            tex.inputs['Color1'].default_value = (0.1, 0.1, 0.1, 1)
            tex.inputs['Color2'].default_value = (0.05, 0.05, 0.05, 1)
            tex.inputs['Mortar'].default_value = (0, 0, 0, 1)
            tex.inputs['Scale'].default_value = 50
            links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
            links.new(tex.outputs['Color'], bsdf.inputs['Roughness'])
            bsdf.inputs['Metallic'].default_value = 0.0
        elif self.mat_type == 'PRINTED':
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-700, 0)
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-500, 0)
            links.new(coord.outputs['UV'], mapping.inputs['Vector'])
            
            tex = nodes.new('ShaderNodeTexWave')
            tex.location = (-300, 0)
            links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            
            tex.inputs['Scale'].default_value = 100
            tex.bands_direction = 'Z'
            bump = nodes.new('ShaderNodeBump')
            bump.location = (-100, -200)
            bump.inputs['Strength'].default_value = 0.2
            links.new(tex.outputs['Color'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            bsdf.inputs['Base Color'].default_value = (0.8, 0.3, 0.0, 1)
            bsdf.inputs['Roughness'].default_value = 0.6
        elif self.mat_type == 'ALUMINUM':
            coord = nodes.new('ShaderNodeTexCoord')
            coord.location = (-700, 0)
            mapping = nodes.new('ShaderNodeMapping')
            mapping.location = (-500, 0)
            links.new(coord.outputs['UV'], mapping.inputs['Vector'])
            
            bsdf.inputs['Base Color'].default_value = (0.9, 0.9, 0.9, 1)
            bsdf.inputs['Metallic'].default_value = 1.0
            bsdf.inputs['Roughness'].default_value = 0.3
            tex = nodes.new('ShaderNodeTexNoise')
            tex.location = (-300, 0)
            links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            
            tex.inputs['Scale'].default_value = 200
            bump = nodes.new('ShaderNodeBump')
            bump.location = (-100, -200)
            bump.inputs['Strength'].default_value = 0.05
            links.new(tex.outputs['Fac'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

        # 4. Assign to selection if in Edit Mode
        if obj.mode == 'EDIT':
            bpy.ops.object.material_slot_assign()

        self.report({'INFO'}, f"Added smart material: {self.mat_type}")
        return {'FINISHED'}

class URDF_OT_Material_LoadTexture(bpy.types.Operator, ImportHelper):
    """Load an image texture into the active material's Base Color"""
    bl_idname = "urdf.material_load_texture"
    bl_label = "Load Texture"
    bl_description = "Load an image file and connect it to the Base Color of the active material"
    
    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.bmp", options={'HIDDEN'})

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        mat = obj.active_material
        if not mat or not mat.use_nodes: 
            self.report({'WARNING'}, "Active material must use nodes.")
            return {'CANCELLED'}
        
        try:
            img = bpy.data.images.load(self.filepath)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load image: {e}")
            return {'CANCELLED'}

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf:
            self.report({'WARNING'}, "No Principled BSDF found in material.")
            return {'CANCELLED'}

        # --- Declarative Node Setup ---
        # Find or create the required nodes for a standard texture setup.
        # This ensures a predictable structure for the UI to find and control.
        tex_coord_node = next((n for n in nodes if n.type == 'TEX_COORD'), None) or nodes.new('ShaderNodeTexCoord')
        mapping_node = next((n for n in nodes if n.type == 'MAPPING'), None) or nodes.new('ShaderNodeMapping')
        tex_node = None
        if bsdf.inputs['Base Color'].is_linked:
            from_node = bsdf.inputs['Base Color'].links[0].from_node
            if from_node.type == 'TEX_IMAGE':
                tex_node = from_node
        if not tex_node:
            tex_node = nodes.new('ShaderNodeTexImage')
        
        # Position nodes for a clean layout
        tex_coord_node.location = (bsdf.location.x - 700, bsdf.location.y)
        mapping_node.location = (bsdf.location.x - 500, bsdf.location.y)
        tex_node.location = (bsdf.location.x - 300, bsdf.location.y)
        
        tex_node.image = img

        # Forcefully create the correct node links, removing any old ones.
        for link in list(bsdf.inputs['Base Color'].links): links.remove(link)
        for link in list(tex_node.inputs['Vector'].links): links.remove(link)
        for link in list(mapping_node.inputs['Vector'].links): links.remove(link)

        links.new(tex_coord_node.outputs['UV'], mapping_node.inputs['Vector'])
        links.new(mapping_node.outputs['Vector'], tex_node.inputs['Vector'])
        links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])

        self.report({'INFO'}, f"Loaded texture '{img.name}' into '{mat.name}'")
        return {'FINISHED'}

class URDF_OT_Material_FromImage(bpy.types.Operator, ImportHelper):
    """Create a new material from an image file"""
    bl_idname = "urdf.material_from_image"
    bl_label = "New Material from Image"
    bl_description = "Create a new material with the selected image as the Base Color"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.tga;*.bmp", options={'HIDDEN'})

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Active object must be a mesh.")
            return {'CANCELLED'}

        # 1. Load Image
        try:
            img = bpy.data.images.load(self.filepath)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load image: {e}")
            return {'CANCELLED'}

        # 2. Create Material Slot and Material
        bpy.ops.object.material_slot_add()
        slot = obj.material_slots[obj.active_material_index]

        mat_name = os.path.splitext(os.path.basename(self.filepath))[0]
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        slot.material = mat

        # 3. Configure Nodes
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        output = nodes.new('ShaderNodeOutputMaterial')
        output.location = (bsdf.location.x + 300, bsdf.location.y)
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.location = (bsdf.location.x - 300, bsdf.location.y)
        tex_node.image = img
        links.new(tex_node.outputs['Color'], bsdf.inputs['Base Color'])

        self.report({'INFO'}, f"Created material '{mat.name}' from '{img.name}'")
        return {'FINISHED'}

class URDF_OT_AddMappingNodes(bpy.types.Operator):
    """Add Texture Coordinate and Mapping nodes to the active material"""
    bl_idname = "urdf.add_mapping_nodes"
    bl_label = "Add Transform Controls"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.active_material and obj.active_material.use_nodes

    def execute(self, context):
        mat = context.active_object.active_material
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Create nodes
        coord = nodes.new('ShaderNodeTexCoord')
        coord.location = (-900, 0)
        mapping = nodes.new('ShaderNodeMapping')
        mapping.location = (-700, 0)
        links.new(coord.outputs['UV'], mapping.inputs['Vector'])
        
        # Try to connect to existing texture nodes
        for node in nodes:
            if node.type.startswith('TEX_') and 'Vector' in node.inputs:
                if not node.inputs['Vector'].is_linked:
                    links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        
        self.report({'INFO'}, "Added mapping nodes")
        return {'FINISHED'}

class URDF_OT_UV_SmartUnwrap(bpy.types.Operator):
    """Apply smart UV unwrapping to the active mesh"""
    bl_idname = "urdf.uv_smart_unwrap"
    bl_label = "Smart UV Unwrap"
    bl_options = {'REGISTER', 'UNDO'}

    method: bpy.props.EnumProperty(
        items=[
            ('SMART', "Smart Project", "Automatic projection based on angle"),
            ('CUBE', "Cube Projection", "Cube mapping"),
            ('CYLINDER', "Cylinder Projection", "Cylindrical mapping"),
            ('SPHERE', "Sphere Projection", "Spherical mapping"),
            ('UNWRAP', "Unwrap", "Standard unwrap (requires seams)"),
        ],
        default='SMART'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        original_mode = obj.mode
        
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        bpy.ops.mesh.select_all(action='SELECT')
        
        if self.method == 'SMART':
            bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
        elif self.method == 'CUBE':
            bpy.ops.uv.cube_project(cube_size=1.0)
        elif self.method == 'CYLINDER':
            bpy.ops.uv.cylinder_project()
        elif self.method == 'SPHERE':
            bpy.ops.uv.sphere_project()
        elif self.method == 'UNWRAP':
            bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.02)
            
        if original_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=original_mode)
            
        self.report({'INFO'}, f"Applied UV: {self.method}")
        return {'FINISHED'}

class URDF_OT_Material_Merge(bpy.types.Operator):
    """Merge all enabled material slots into a single composite material"""
    bl_idname = "urdf.material_merge"
    bl_label = "Composite All Layers"
    bl_description = "Combines all enabled material layers into a single composite material (preserving settings) and deletes old layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or not obj.material_slots:
            return {'CANCELLED'}
        
        comp_mat_name = f"Composite_{obj.name}"
        
        # Filter valid source slots
        source_slots = [
            slot for slot in obj.material_slots 
            if slot.material and slot.material.name != comp_mat_name and getattr(slot, "urdf_enabled", True)
        ]

        if not source_slots:
            self.report({'WARNING'}, "No enabled material layers to merge.")
            return {'CANCELLED'}

        # Create or Reset Composite Material
        comp_mat = bpy.data.materials.get(comp_mat_name)
        if not comp_mat:
            comp_mat = bpy.data.materials.new(name=comp_mat_name)
        
        comp_mat.use_nodes = True
        tree = comp_mat.node_tree
        tree.nodes.clear()
        
        output_node = tree.nodes.new('ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        # Stack Shaders
        current_shader_socket = None
        x_offset = -300
        
        def copy_material_to_group(mat, group_tree):
            """Helper to copy a material's node tree into a node group."""
            group_tree.nodes.clear()
            
            # Create Group Outputs
            g_out = group_tree.nodes.new('NodeGroupOutput')
            g_out.location = (300, 0)
            group_tree.interface.new_socket(name="Surface", in_out='OUTPUT', socket_type='NodeSocketShader')
            group_tree.interface.new_socket(name="Alpha", in_out='OUTPUT', socket_type='NodeSocketFloat')
            
            # Copy nodes
            node_map = {}
            src_tree = mat.node_tree
            
            for node in src_tree.nodes:
                if node.type == 'OUTPUT_MATERIAL': continue
                
                new_node = group_tree.nodes.new(node.bl_idname)
                new_node.location = node.location
                new_node.label = node.label
                new_node.name = node.name
                
                # Copy properties
                for prop in node.bl_rna.properties:
                    if not prop.is_readonly:
                        try:
                            setattr(new_node, prop.identifier, getattr(node, prop.identifier))
                        except: pass
                
                # Copy inputs defaults
                for i, inp in enumerate(node.inputs):
                    if hasattr(inp, 'default_value'):
                        try:
                            new_node.inputs[i].default_value = inp.default_value
                        except: pass
                
                if node.type == 'TEX_IMAGE' and node.image:
                    new_node.image = node.image
                
                node_map[node] = new_node
            
            # Reconnect links
            for link in src_tree.links:
                if link.from_node in node_map and link.to_node in node_map:
                    try:
                        group_tree.links.new(node_map[link.from_node].outputs[link.from_socket.name],
                                             node_map[link.to_node].inputs[link.to_socket.name])
                    except: pass
            
            # Connect to Group Output
            # 1. Surface
            mat_out = next((n for n in src_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if mat_out and mat_out.inputs['Surface'].is_linked:
                link = mat_out.inputs['Surface'].links[0]
                if link.from_node in node_map:
                    group_tree.links.new(node_map[link.from_node].outputs[link.from_socket.name], g_out.inputs['Surface'])
            
            # 2. Alpha (Find Principled BSDF)
            bsdf = next((n for n in node_map.values() if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf:
                if bsdf.inputs['Alpha'].is_linked:
                    link = bsdf.inputs['Alpha'].links[0]
                    # Connect the source of the alpha link to the group output
                    group_tree.links.new(link.from_node.outputs[link.from_socket.name], g_out.inputs['Alpha'])
                else:
                    # Create a value node for constant alpha
                    val = group_tree.nodes.new('ShaderNodeValue')
                    val.outputs[0].default_value = bsdf.inputs['Alpha'].default_value
                    val.location = (g_out.location.x - 200, g_out.location.y - 200)
                    group_tree.links.new(val.outputs[0], g_out.inputs['Alpha'])
            else:
                # Default Alpha 1.0
                val = group_tree.nodes.new('ShaderNodeValue')
                val.outputs[0].default_value = 1.0
                val.location = (g_out.location.x - 200, g_out.location.y - 200)
                group_tree.links.new(val.outputs[0], g_out.inputs['Alpha'])

        for i, slot in enumerate(source_slots):
            mat = slot.material
            if not mat or not mat.use_nodes: continue
            
            # Create a Group Node for each material
            group_node = tree.nodes.new('ShaderNodeGroup')
            group_node.location = (x_offset, i * -300)
            group_node.label = mat.name
            
            # Create a unique node group for this layer to preserve settings
            # We use a unique name to avoid conflicts if the material is edited later
            group_name = f"URDF_Layer_{mat.name}_{obj.name}_{i}"
            # Remove old group if it exists to ensure fresh copy
            if group_name in bpy.data.node_groups:
                bpy.data.node_groups.remove(bpy.data.node_groups[group_name])
            
            new_group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
            copy_material_to_group(mat, new_group)
            group_node.node_tree = new_group
            
            # Get outputs
            layer_shader = group_node.outputs.get('Surface')
            layer_alpha = group_node.outputs.get('Alpha')
            
            if not layer_shader: continue
            
            if current_shader_socket is None:
                current_shader_socket = layer_shader
            else:
                # Mix with previous layer
                mix_node = tree.nodes.new('ShaderNodeMixShader')
                mix_node.location = (x_offset + 200, i * -300)
                
                # Use the layer's alpha as the mix factor
                if layer_alpha:
                    tree.links.new(layer_alpha, mix_node.inputs['Fac'])
                else:
                    mix_node.inputs['Fac'].default_value = 1.0
                
                tree.links.new(current_shader_socket, mix_node.inputs[1])
                tree.links.new(layer_shader, mix_node.inputs[2])
                current_shader_socket = mix_node.outputs['Shader']
            
            x_offset -= 400

        if current_shader_socket:
            tree.links.new(current_shader_socket, output_node.inputs['Surface'])

        # Assign Composite Material to a new slot if needed
        comp_slot_index = obj.material_slots.find(comp_mat_name)
        if comp_slot_index == -1:
            bpy.ops.object.material_slot_add()
            comp_slot_index = len(obj.material_slots) - 1
        
        obj.material_slots[comp_slot_index].material = comp_mat
        
        # Move composite slot to the bottom to ensure stable indices for removal
        if comp_slot_index != len(obj.material_slots) - 1:
            obj.active_material_index = comp_slot_index
            while obj.active_material_index < len(obj.material_slots) - 1:
                bpy.ops.object.material_slot_move(direction='DOWN')
            comp_slot_index = len(obj.material_slots) - 1
        
        # Assign all faces to composite
        for poly in obj.data.polygons:
            poly.material_index = comp_slot_index
            
        # Remove source slots (iterate backwards to avoid index shifting issues)
        # We exclude the last slot (which is our new composite)
        for i in range(len(obj.material_slots) - 2, -1, -1):
            slot = obj.material_slots[i]
            # Only remove if it was enabled and is not the composite itself
            if getattr(slot, "urdf_enabled", True) and slot.material.name != comp_mat_name:
                obj.active_material_index = i
                bpy.ops.object.material_slot_remove()
            
        self.report({'INFO'}, f"Composited layers into '{comp_mat_name}'")
        return {'FINISHED'}

class URDF_OT_Material_Add(bpy.types.Operator):
    """Add a new material slot (Blank or Existing)"""
    bl_idname = "urdf.material_add"
    bl_label = "Add Material"
    bl_description = "Adds a new material slot. Use properties to select existing material."
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(items=[('NEW', "New", ""), ('EXISTING', "Existing", "")], default='NEW')
    
    def get_materials(self, context):
        return [(mat.name, mat.name, "") for mat in bpy.data.materials]

    material_name: bpy.props.EnumProperty(items=get_materials, name="Material")

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj: return {'CANCELLED'}

        bpy.ops.object.material_slot_add()
        
        if self.mode == 'NEW':
            mat = bpy.data.materials.new(name=f"Mat_{obj.name}")
            mat.use_nodes = True
            # --- AI Editor Note: Add default nodes for a valid base material ---
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            # Ensure there's an output node
            output = nodes.get("Material Output") or nodes.new('ShaderNodeOutputMaterial')
            # Create and link a Principled BSDF
            bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            bsdf.location = output.location.x - 250, output.location.y
            links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
        else:
            mat = bpy.data.materials.get(self.material_name)
            
        if mat:
            obj.material_slots[obj.active_material_index].material = mat
            
        if obj.mode == 'EDIT':
            bpy.ops.object.material_slot_assign()
            
        return {'FINISHED'}
    
    def invoke(self, context, event):
        if self.mode == 'EXISTING':
            return context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

class URDF_UL_Mat_List(bpy.types.UIList):
    """Simple UI List for Materials"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        slot = item
        mat = slot.material
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(slot, "urdf_enabled", text="")
            row.prop(slot, "material", text="", emboss=False, icon='MATERIAL')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class URDF_UL_SlinkyHooks_List(bpy.types.UIList):
    """Simple UI List for Slinky Hooks"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        hook = item.target
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            if hook:
                row.label(text=hook.name, icon='EMPTY_AXIS')
            else:
                row.label(text="(Empty Slot)", icon='ERROR')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class URDF_OT_Paint_SetupBrush(bpy.types.Operator):
    """Configure a texture paint brush with a specific preset"""
    bl_idname = "urdf.paint_setup_brush"
    bl_label = "Setup Smart Brush"
    bl_description = "Sets up the active brush with texture and settings for painting"
    bl_options = {'REGISTER', 'UNDO'}
    
    brush_type: bpy.props.EnumProperty(
        items=[
            ('DIRT', "Dirt/Grime", "Dark, low opacity, cloudy pattern"),
            ('SCRATCH', "Scratches", "Light, high contrast, noise pattern"),
            ('RUST', "Rust", "Reddish-brown, musgrave pattern"),
            ('OIL', "Oil Stain", "Dark, glossy, smooth"),
        ]
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Select a mesh object.")
            return {'CANCELLED'}
            
        # 0. Ensure UV Map (Crucial for painting)
        if not obj.data.uv_layers:
            bpy.ops.mesh.uv_texture_add()
            
        # 1. Ensure Material and Image
        mat = obj.active_material or bpy.data.materials.new(name=f"Paint_{obj.name}")
        if not mat:
            bpy.ops.urdf.add_smart_material(mat_type='PLASTIC')
            mat = obj.active_material
        if not mat.use_nodes: mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf: return {'CANCELLED'}
            
        # Check for image texture connected to Base Color
        base_color_socket = bsdf.inputs['Base Color']
        img_node = next((l.from_node for l in base_color_socket.links if l.from_node.type == 'TEX_IMAGE'), None)
        
        if not img_node:
            img_node = nodes.new('ShaderNodeTexImage')
            img_node.location = (bsdf.location.x - 300, bsdf.location.y)
            img = bpy.data.images.new(name=f"{obj.name}_BaseColor", width=2048, height=2048)
            img.generated_color = base_color_socket.default_value
            img_node.image = img
            mat.node_tree.links.new(img_node.outputs['Color'], base_color_socket)

        # 2. Enter Texture Paint Mode
        if obj.mode != 'TEXTURE_PAINT':
            bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
            
        # 3. Setup Brush
        brush = context.tool_settings.image_paint.brush
        if not brush:
            # Fix: Ensure a brush exists to make the feature usable
            if bpy.data.brushes:
                brush = bpy.data.brushes[0]
            else:
                brush = bpy.data.brushes.new(name="URDF_Smart_Brush", mode='TEXTURE_PAINT')
            context.tool_settings.image_paint.brush = brush
            
        if self.brush_type == 'DIRT':
            brush.color = (0.1, 0.08, 0.05); brush.strength = 0.4; brush.blend = 'MIX'
            tex = bpy.data.textures.get("URDF_Brush_Dirt") or bpy.data.textures.new("URDF_Brush_Dirt", type='CLOUDS')
            tex.noise_scale = 0.5; brush.texture = tex
        elif self.brush_type == 'SCRATCH':
            brush.color = (0.8, 0.8, 0.8); brush.strength = 0.8; brush.blend = 'LIGHTEN'
            tex = bpy.data.textures.get("URDF_Brush_Scratch") or bpy.data.textures.new("URDF_Brush_Scratch", type='NOISE')
            brush.texture = tex
        elif self.brush_type == 'RUST':
            brush.color = (0.4, 0.15, 0.05); brush.strength = 0.6; brush.blend = 'MIX'
            tex = bpy.data.textures.get("URDF_Brush_Rust") or bpy.data.textures.new("URDF_Brush_Rust", type='MUSGRAVE')
            tex.noise_scale = 0.8; brush.texture = tex
        elif self.brush_type == 'OIL':
            brush.color = (0.05, 0.05, 0.05); brush.strength = 0.5; brush.blend = 'MIX'; brush.texture = None

        self.report({'INFO'}, f"Brush set to {self.brush_type}")
        return {'FINISHED'}

class OPS_OT_ExportGazeboWorld(bpy.types.Operator):
    """Exports a simple Gazebo world file containing the robot"""
    bl_idname = "urdf.export_gazebo_world"
    bl_label = "Export Gazebo World"
    bl_options = {'INTERNAL'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context: bpy.types.Context) -> Set[str]:
        rig = context.scene.urdf_active_rig
        if not rig:
            self.report({'ERROR'}, "No active rig selected.")
            return {'CANCELLED'}

        robot_name = rig.name

        sdf = ET.Element('sdf', version='1.6')
        world = ET.SubElement(sdf, 'world', name='default')
        
        # Add lighting
        light = ET.SubElement(world, 'light', name='sun', type='directional')
        ET.SubElement(light, 'cast_shadows').text = 'true'
        ET.SubElement(light, 'pose').text = '0 0 10 0 0 0'
        ET.SubElement(light, 'direction').text = '-0.5 -0.5 -1'
        ET.SubElement(ET.SubElement(light, 'diffuse'), 'a').text = '0.8 0.8 0.8 1'
        ET.SubElement(ET.SubElement(light, 'specular'), 'a').text = '0.2 0.2 0.2 1'

        # Add ground plane
        include_ground = ET.SubElement(world, 'include')
        ET.SubElement(include_ground, 'uri').text = 'model://ground_plane'

        # Include the robot model
        include_robot = ET.SubElement(world, 'include')
        ET.SubElement(include_robot, 'uri').text = f'model://{robot_name}'
        ET.SubElement(include_robot, 'name').text = robot_name
        ET.SubElement(include_robot, 'pose').text = '0 0 0 0 0 0'

        tree = ET.ElementTree(sdf)
        ET.indent(tree, space="  ", level=0)
        tree.write(self.filepath, encoding='utf-8', xml_declaration=True)

        self.report({'INFO'}, f"Exported Gazebo world to {self.filepath}")
        return {'FINISHED'}

class OPS_OT_LinkChainDriver(bpy.types.Operator):
    """
    Links the chain's animation to the rotation of a selected object (e.g., a sprocket).
    Calculates the linear motion based on the driver's radius.
    """
    bl_idname = "urdf.link_chain_driver"
    bl_label = "Link Driver"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        path_obj = context.active_object
        props = path_obj.urdf_mech_props
        driver_obj = props.chain_drive_target

        # If no specific driver is selected, try to use the first wrap object
        if not driver_obj and len(props.chain_wrap_items) > 0:
            driver_obj = props.chain_wrap_items[0].target
            props.chain_drive_target = driver_obj

        if not driver_obj:
            self.report({'WARNING'}, "No driver object selected or found in wrap list.")
            return {'CANCELLED'}

        # Determine the effective radius for the driver
        radius = 1.0
        if hasattr(driver_obj, "urdf_mech_props") and driver_obj.urdf_mech_props.is_part:
            # If it's a generated gear/pulley, use its parametric radius
            radius = driver_obj.urdf_mech_props.radius
        else:
            # Otherwise, estimate from dimensions (assuming Z-axis rotation, so X/Y radius)
            radius = (driver_obj.dimensions.x + driver_obj.dimensions.y) / 4.0

        # AI Editor Note: Fallback for objects with zero dimensions (like Empties) to ensure movement.
        if radius < 0.001: radius = 1.0

        # Create the driver on the chain's animation offset property
        # AI Editor Note: Remove existing driver first to ensure a clean update.
        # This fixes the issue where the driver object couldn't be changed.
        path_obj.driver_remove('["urdf_native_anim_offset"]')
        
        # This property drives the Geometry Nodes modifier input
        fcurve_anim = path_obj.driver_add('["urdf_native_anim_offset"]')
        driver_anim = fcurve_anim.driver
        
        # AI Editor Note: Clear existing variables to ensure a clean switch when changing drivers.
        # This fixes the issue where the driver would stick to the previous object.
        for v in list(driver_anim.variables):
            driver_anim.variables.remove(v)
            
        driver_anim.type = 'SCRIPTED'

        var_rot = driver_anim.variables.new()
        var_rot.name = "rotation"
        # AI Editor Note: Use SINGLE_PROP for raw Euler rotation to avoid 
        # -180/180 degree wrapping (snapping) that occurs with TRANSFORMS.
        var_rot.type = 'SINGLE_PROP'
        var_rot.targets[0].id = driver_obj
        # AI Editor Note: Target the Z-axis of the Euler rotation directly via data_path string.
        # DriverTarget does not have a 'data_path_index' attribute.
        var_rot.targets[0].data_path = "rotation_euler[2]"

        # Store the calculated radius. This might trigger the update callback,
        # but we call it explicitly below to ensure the expression is set correctly
        # even if the radius hasn't changed.
        props.chain_drive_radius = radius

        # Apply the driver expression using the new settings (Radius, Ratio, Invert)
        update_chain_driver_settings(props, context)

        self.report({'INFO'}, f"Linked chain to '{driver_obj.name}' with radius {radius:.3f}")
        return {'FINISHED'}

class OPS_OT_AddBoolean(bpy.types.Operator):
    bl_idname = "urdf.add_boolean"
    bl_label = "Add Boolean"
    bl_options = {'REGISTER', 'UNDO'}
    operation: bpy.props.EnumProperty(items=[('DIFFERENCE', "Cut", ""), ('UNION', "Join", ""), ('INTERSECT', "Intersect", "")])

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            cls.poll_message_set("Active object must be a mesh.")
            return False
        
        selected_meshes = [obj for obj in context.selected_objects if obj != active_obj and obj.type == 'MESH']
        if not selected_meshes:
            cls.poll_message_set("Select at least one other mesh object.")
            return False
            
        return True

    def execute(self, context: bpy.types.Context) -> Set[str]:
        active = context.active_object
        # The objects to be used by the modifier are the selected ones, excluding the active one.
        selected = [o for o in context.selected_objects if o != active and o.type == 'MESH']

        for target in selected:
            mod = active.modifiers.new(name=f"{BOOL_PREFIX}{target.name}", type='BOOLEAN')
            mod.operation = self.operation
            mod.object = target
            mod.solver = 'EXACT'
            target.display_type = 'BOUNDS'
            target.hide_render = True
            
        self.report({'INFO'}, f"Added {len(selected)} boolean modifier(s) to '{active.name}'.")
        return {'FINISHED'}

class URDF_OT_AddParametricAnchor(bpy.types.Operator):
    """Creates an Empty object and adds a Hook modifier to the selected mesh elements"""
    bl_idname = "urdf.add_parametric_anchor"
    bl_label = "Attach Hook to Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'EDIT_MESH'

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        # Get selection center
        bm = bmesh.from_edit_mesh(obj.data)
        selected_verts = [v for v in bm.verts if v.select]
        
        if not selected_verts:
            self.report({'WARNING'}, "No vertices/edges/faces selected.")
            return {'CANCELLED'}
            
        center = mathutils.Vector((0,0,0))
        for v in selected_verts:
            center += v.co
        center /= len(selected_verts)
        
        # Transform to world space
        world_center = obj.matrix_world @ center
        
        # Switch to Object Mode to create Empty and VG
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create Empty
        empty = bpy.data.objects.new(f"Hook_{obj.name}", None)
        empty.location = world_center
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 0.1
        context.collection.objects.link(empty)
        
        # Create Vertex Group for the selection
        # This is crucial for the "Apply Transforms" placement logic to work later
        vg_name = f"Hook_Group_{empty.name}"
        vg = obj.vertex_groups.new(name=vg_name)
        
        # Assign selected vertices to the group
        selected_indices = [v.index for v in obj.data.vertices if v.select]
        if selected_indices:
            vg.add(selected_indices, 1.0, 'REPLACE')
        
        # Add Hook Modifier manually to ensure VG usage
        mod = obj.modifiers.new(name="Hook", type='HOOK')
        mod.object = empty
        mod.vertex_group = vg_name
        
        # Reset Hook to bind correctly to the current relative positions
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        
        # Select vertices via VG to ensure correct reset context
        obj.vertex_groups.active_index = vg.index
        bpy.ops.object.vertex_group_select()
        
        bpy.ops.object.hook_reset(modifier=mod.name)
        
        # Return to Object Mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Select the Empty for immediate manipulation
        bpy.ops.object.select_all(action='DESELECT')
        empty.select_set(True)
        context.view_layer.objects.active = empty
        
        self.report({'INFO'}, f"Attached Hook '{empty.name}' to selection")
        return {'FINISHED'}

class URDF_OT_AddMarker(bpy.types.Operator):
    """Creates an Empty marker at each selected vertex"""
    bl_idname = "urdf.add_marker"
    bl_label = "Attach Marker to Vertex"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == 'EDIT_MESH'

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        # --- AI Editor Note: Ensure Vertex Mode ---
        # Convert any Edge/Face selection to Vertices to handle "all types" and "any amount".
        bpy.ops.mesh.select_mode(type='VERT')
        
        # Get selected vertices
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        
        # AI Editor Note: Store indices before mode switch.
        # BMesh data is invalidated when switching to Object Mode.
        selected_indices = [v.index for v in bm.verts if v.select]
        
        if not selected_indices:
            self.report({'WARNING'}, "No vertices selected.")
            return {'CANCELLED'}
            
        # Switch to Object Mode for parenting
        bpy.ops.object.mode_set(mode='OBJECT')
        
        created_count = 0
        created_empties = []
        
        for idx in selected_indices:
            # Create Empty
            empty = bpy.data.objects.new(f"Marker_{obj.name}_{idx}", None)
            empty.empty_display_type = 'PLAIN_AXES' # AI Editor Note: Changed to PLAIN_AXES per request
            empty.empty_display_size = 0.1
            context.collection.objects.link(empty)
            
            # Parent to specific vertex using native API
            empty.parent = obj
            empty.parent_type = 'VERTEX'
            empty.parent_vertices = (idx, 0, 0)
            
            # AI Editor Note: Reset location to (0,0,0) to snap exactly to the parent vertex.
            # When parented to a vertex, local (0,0,0) is the vertex position.
            empty.location = (0, 0, 0)
            
            created_empties.append(empty)
            created_count += 1
        
        # Finalize selection
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all created markers for convenience
        for e in created_empties:
            e.select_set(True)
            
        if created_empties:
            context.view_layer.objects.active = created_empties[-1]
        else:
            obj.select_set(True)
            context.view_layer.objects.active = obj
        
        self.report({'INFO'}, f"Attached {created_count} Markers to vertices")
        return {'FINISHED'}

class URDF_OT_ToggleHookPlacement(bpy.types.Operator):
    """Toggle placement mode for the hook anchor. Move the empty without deforming the mesh, then stop to rebind."""
    bl_idname = "urdf.toggle_hook_placement"
    bl_label = "Start/Stop Hook Placement Mode"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object and context.active_object.type == 'EMPTY'

    def execute(self, context: bpy.types.Context) -> Set[str]:
        empty = context.active_object
        scene = context.scene
        
        # Toggle state
        is_starting = not scene.urdf_hook_placement_mode
        scene.urdf_hook_placement_mode = is_starting
        
        if is_starting:
            # Start Placement: Apply modifiers to bake deformation, allowing empty to move freely
            target_meshes = []
            hook_data = []
            
            for obj in context.scene.objects:
                if obj.type == 'MESH':
                    for mod in obj.modifiers:
                        if mod.type == 'HOOK' and mod.object == empty:
                            target_meshes.append((obj, mod))
            
            if not target_meshes:
                self.report({'WARNING'}, "No meshes found hooked to this Empty.")
                scene.urdf_hook_placement_mode = False
                return {'CANCELLED'}

            for mesh, mod in target_meshes:
                # Store data to re-create the hook later
                hook_data.append({
                    "mesh_name": mesh.name,
                    "vg_name": mod.vertex_group
                })
                
                # Apply the modifier to bake the current shape
                try:
                    with context.temp_override(object=mesh):
                        bpy.ops.object.modifier_apply(modifier=mod.name)
                except Exception as e:
                    self.report({'ERROR'}, f"Failed to apply hook on {mesh.name}: {e}")
            
            # Store hook data on the empty
            empty["urdf_hook_data"] = hook_data
            self.report({'INFO'}, "Hook Placement Started. Deformation applied. Move the Empty, then click Stop.")
            
        else:
            # Stop Placement: Re-create Hook modifiers at new empty position
            original_active = context.view_layer.objects.active
            original_selected = context.selected_objects
            
            # Ensure Object Mode to start
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
                
            bpy.ops.object.select_all(action='DESELECT')
            
            hook_data = empty.get("urdf_hook_data", [])
            
            for item in hook_data:
                mesh = bpy.data.objects.get(item["mesh_name"])
                if not mesh: continue
                
                vg_name = item["vg_name"]
                
                # Create new Hook modifier
                mod = mesh.modifiers.new(name="Hook", type='HOOK')
                mod.object = empty
                if vg_name:
                    mod.vertex_group = vg_name

                context.view_layer.objects.active = mesh
                mesh.select_set(True)
                
                # Resetting the hook requires Edit Mode and selecting the bound vertices
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='DESELECT')
                    
                    # Select vertices based on VG if available
                    if vg_name and vg_name in mesh.vertex_groups:
                        mesh.vertex_groups.active_index = mesh.vertex_groups[vg_name].index
                        bpy.ops.object.vertex_group_select()
                    else:
                        # Fallback: Select all if no VG (though AddParametricAnchor creates one)
                        bpy.ops.mesh.select_all(action='SELECT')

                    # Reset the hook (rebinds to current empty position)
                    bpy.ops.object.hook_reset(modifier=mod.name)
                except Exception as e:
                    self.report({'WARNING'}, f"Could not reset hook on {mesh.name}: {e}")
                finally:
                    # Always return to Object Mode
                    if context.mode != 'OBJECT':
                        bpy.ops.object.mode_set(mode='OBJECT')
                
                mesh.select_set(False)
            
            # Cleanup
            if "urdf_hook_data" in empty:
                del empty["urdf_hook_data"]

            # Restore state
            if original_active and original_active.name in context.scene.objects:
                context.view_layer.objects.active = original_active
            for o in original_selected:
                if o.name in context.scene.objects:
                    o.select_set(True)
            self.report({'INFO'}, "Hook Placement Stopped. Anchor rebound.")
            
        return {'FINISHED'}

class URDF_OT_CleanupAnchor(bpy.types.Operator):
    """Removes the anchor Empty and cleans up related Hook modifiers and Vertex Groups"""
    bl_idname = "urdf.cleanup_anchor"
    bl_label = "Remove Selected Hook/Marker"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.selected_objects

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Collect all Empties from selection (Hooks/Markers)
        empties = [o for o in context.selected_objects if o.type == 'EMPTY']
        
        # Fallback to active object if no empties selected but active is empty
        if not empties and context.active_object and context.active_object.type == 'EMPTY':
            empties = [context.active_object]
            
        if not empties:
            self.report({'WARNING'}, "No hooks/markers (Empties) selected.")
            return {'CANCELLED'}

        cleaned_count = 0
        
        for empty in empties:
            # 1. Find meshes affected by this anchor (Hook Modifier)
            meshes_to_clean = []
            for obj in context.scene.objects:
                if obj.type == 'MESH':
                    for mod in obj.modifiers:
                        if mod.type == 'HOOK' and mod.object == empty:
                            meshes_to_clean.append((obj, mod))
            
            # 2. Clean up meshes
            for obj, mod in meshes_to_clean:
                vg_name = mod.vertex_group
                try:
                    obj.modifiers.remove(mod)
                except:
                    pass
                
                # Remove Vertex Group if it exists
                if vg_name:
                    vg = obj.vertex_groups.get(vg_name)
                    if vg:
                        obj.vertex_groups.remove(vg)
            
            # 3. Delete the Empty
            bpy.data.objects.remove(empty, do_unlink=True)
            cleaned_count += 1
        
        self.report({'INFO'}, f"Removed {cleaned_count} hooks/markers.")
        return {'FINISHED'}

class URDF_OT_BakeAnchor(bpy.types.Operator):
    """Applies the hook deformation to the mesh geometry (Bake)"""
    bl_idname = "urdf.bake_anchor"
    bl_label = "Bake Anchor (Apply)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None

    def execute(self, context: bpy.types.Context) -> Set[str]:
        targets = context.selected_objects
        if not targets: targets = [context.active_object]
        
        meshes_to_process = set()
        
        # Identify meshes to process
        for obj in targets:
            if obj.type == 'MESH':
                meshes_to_process.add(obj)
            elif obj.type == 'EMPTY':
                for m_obj in context.scene.objects:
                    if m_obj.type == 'MESH':
                        for mod in m_obj.modifiers:
                            if mod.type == 'HOOK' and mod.object == obj:
                                meshes_to_process.add(m_obj)
        
        if not meshes_to_process:
            self.report({'WARNING'}, "No meshes with hooks found.")
            return {'CANCELLED'}

        processed_count = 0
        
        # Ensure Object Mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        # Process each mesh
        for mesh_obj in meshes_to_process:
            mods_to_apply = []
            hooks_to_restore = []

            for mod in mesh_obj.modifiers:
                if mod.type == 'HOOK':
                    # Apply if mesh selected OR if hook is linked to selected empty
                    if mesh_obj in targets or (mod.object in targets):
                        mods_to_apply.append(mod.name)
                        # Save state to restore after baking
                        hooks_to_restore.append({
                            'name': mod.name,
                            'object': mod.object,
                            'vertex_group': mod.vertex_group,
                            'strength': mod.strength,
                            'falloff_type': mod.falloff_type,
                            'falloff_radius': mod.falloff_radius,
                            'uniform': mod.use_falloff_uniform
                        })
            
            if mods_to_apply:
                context.view_layer.objects.active = mesh_obj
                for mod_name in mods_to_apply:
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod_name)
                        processed_count += 1
                    except Exception as e:
                        self.report({'WARNING'}, f"Failed to apply {mod_name}: {e}")
                
                # Restore hooks to maintain parametric control over the new rest pose
                for hook_data in reversed(hooks_to_restore):
                    try:
                        new_mod = mesh_obj.modifiers.new(name=hook_data['name'], type='HOOK')
                        new_mod.object = hook_data['object']
                        if hook_data['vertex_group']:
                            new_mod.vertex_group = hook_data['vertex_group']
                        new_mod.strength = hook_data['strength']
                        new_mod.falloff_type = hook_data['falloff_type']
                        new_mod.falloff_radius = hook_data['falloff_radius']
                        new_mod.use_falloff_uniform = hook_data['uniform']
                        
                        # Reset (Rebind) to current state
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.select_all(action='DESELECT')
                        if hook_data['vertex_group'] and hook_data['vertex_group'] in mesh_obj.vertex_groups:
                            mesh_obj.vertex_groups.active_index = mesh_obj.vertex_groups[hook_data['vertex_group']].index
                            bpy.ops.object.vertex_group_select()
                        else:
                            bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.object.hook_reset(modifier=new_mod.name)
                        bpy.ops.object.mode_set(mode='OBJECT')
                        
                        # Move to top to maintain stack order logic
                        bpy.ops.object.modifier_move_to_index(modifier=new_mod.name, index=0)
                    except Exception as e:
                        self.report({'ERROR'}, f"Failed to restore hook {hook_data['name']}: {e}")
        
        self.report({'INFO'}, f"Baked {processed_count} hook modifiers (Pose Updated).")
        return {'FINISHED'}

def setup_dimension_gn(text_obj: bpy.types.Object, obj_a: bpy.types.Object, obj_b: bpy.types.Object, context: bpy.types.Context) -> None:
    """
    Creates a Geometry Nodes setup to dynamically display the distance between two objects as text.
    """
    gn_name = "URDF_Dynamic_Dimension_GN"
    gn_group = bpy.data.node_groups.get(gn_name)
    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_name, type='GeometryNodeTree')
        
    # AI Editor Note: Only build if missing or empty to preserve socket IDs for existing users.
    # FIX: Check for missing "Object Scale" socket to ensure compatibility with new features.
    needs_build = False
    if not gn_group.nodes:
        needs_build = True
    elif gn_group.interface and not gn_group.interface.items_tree.get("Object Scale"):
        needs_build = True

    if needs_build:
        gn_group.nodes.clear()
        gn_group.interface.clear()

        # --- Interface ---
        iface = gn_group.interface
        iface.new_socket(name="Object A", in_out="INPUT", socket_type='NodeSocketObject')
        iface.new_socket(name="Object B", in_out="INPUT", socket_type='NodeSocketObject')
        scale_sock = iface.new_socket(name="Scale", in_out="INPUT", socket_type='NodeSocketFloat')
        scale_sock.default_value = 1.0
        obj_scale_sock = iface.new_socket(name="Object Scale", in_out="INPUT", socket_type='NodeSocketFloat')
        obj_scale_sock.default_value = 1.0
        suffix_sock = iface.new_socket(name="Suffix", in_out="INPUT", socket_type='NodeSocketString')
        suffix_sock.default_value = "m"
        iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

        # --- Nodes ---
        nodes = gn_group.nodes
        links = gn_group.links

        g_in = nodes.new('NodeGroupInput')
        g_in.location = (-800, 0)
        g_out = nodes.new('NodeGroupOutput')
        g_out.location = (800, 0)

        # Get Locations
        info_a = nodes.new('GeometryNodeObjectInfo')
        info_a.location = (-600, 100)
        info_a.transform_space = 'RELATIVE'
        
        info_b = nodes.new('GeometryNodeObjectInfo')
        info_b.location = (-600, -100)
        info_b.transform_space = 'RELATIVE'

        # Calculate Distance
        dist = nodes.new('ShaderNodeVectorMath')
        dist.operation = 'DISTANCE'
        dist.location = (-400, 0)
        
        # --- NEW: Scale Compensation ---
        # AI Editor Note: Use explicit input for Object Scale to ensure reliability.
        # Relative distance (from Object Info) is divided by object scale.
        # We must multiply by Object Scale to get World Distance.
        
        math_compensate = nodes.new('ShaderNodeMath')
        math_compensate.operation = 'MULTIPLY'
        math_compensate.location = (-200, 0)

        # Apply Unit Scale
        math_scale = nodes.new('ShaderNodeMath')
        math_scale.operation = 'MULTIPLY'
        math_scale.location = (0, 0)

        # Value to String
        val_to_str = nodes.new('FunctionNodeValueToString')
        val_to_str.inputs['Decimals'].default_value = 3
        val_to_str.location = (200, 0)

        # Join Suffix
        join_str = nodes.new('GeometryNodeStringJoin')
        join_str.location = (400, 0)
        join_str.inputs['Delimiter'].default_value = " "

        # String to Curves
        str_to_curve = nodes.new('GeometryNodeStringToCurves')
        str_to_curve.location = (600, 0)
        str_to_curve.align_x = 'CENTER'
        str_to_curve.align_y = 'MIDDLE'
        str_to_curve.inputs['Size'].default_value = 0.15 # Text Size

        # Fill Curve
        fill = nodes.new('GeometryNodeFillCurve')
        fill.location = (800, 0)
        fill.mode = 'NGONS'
        
        # Set Material
        set_mat = nodes.new('GeometryNodeSetMaterial')
        set_mat.location = (1000, 0)
        mat = get_or_create_text_material(context)
        set_mat.inputs['Material'].default_value = mat

        # --- Links ---
        links.new(g_in.outputs['Object A'], info_a.inputs['Object'])
        links.new(g_in.outputs['Object B'], info_b.inputs['Object'])
        
        links.new(info_a.outputs['Location'], dist.inputs[0])
        links.new(info_b.outputs['Location'], dist.inputs[1])
        
        # Link Scale Compensation
        links.new(dist.outputs['Value'], math_compensate.inputs[0])
        links.new(g_in.outputs['Object Scale'], math_compensate.inputs[1])
        
        links.new(math_compensate.outputs['Value'], math_scale.inputs[0])
        links.new(g_in.outputs['Scale'], math_scale.inputs[1])
        
        links.new(math_scale.outputs['Value'], val_to_str.inputs['Value'])
        
        links.new(val_to_str.outputs['String'], join_str.inputs['Strings'])
        links.new(g_in.outputs['Suffix'], join_str.inputs['Strings'])
        
        links.new(join_str.outputs['String'], str_to_curve.inputs['String'])
        links.new(str_to_curve.outputs['Curve Instances'], fill.inputs['Curve'])
        links.new(fill.outputs['Mesh'], set_mat.inputs['Geometry'])
        links.new(set_mat.outputs['Geometry'], g_out.inputs['Geometry'])

    # --- Apply Modifier ---
    mod = text_obj.modifiers.new(name="Dynamic_Dimension", type='NODES')
    mod.node_group = gn_group
    
    # AI Editor Note: Robustly assign objects using socket identifiers
    if hasattr(gn_group, "interface"):
        for item in gn_group.interface.items_tree:
            if item.name == "Object A":
                mod[item.identifier] = obj_a
            elif item.name == "Object B":
                mod[item.identifier] = obj_b

def get_or_create_text_material(context):
    """Ensures the shared text material exists and returns it."""
    mat_name = "URDF_Text_Material"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
    
    # AI Editor Note: Always sync color to scene property to prevent mismatch (e.g. white viewport vs black property)
    color = getattr(context.scene, "urdf_text_color", (0.0, 0.0, 0.0, 1.0))
    if mat.use_nodes and mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs['Base Color'].default_value = color
            bsdf.inputs['Emission Color'].default_value = color
            bsdf.inputs['Emission Strength'].default_value = 1.0
    
    # AI Editor Note: Update viewport display color for Solid mode so changes are visible immediately
    mat.diffuse_color = color
    return mat

def create_arrow_mesh_data():
    """Creates a wireframe arrow mesh with origin at the tip."""
    mesh_name = "URDF_Arrow_Mesh"
    mesh = bpy.data.meshes.get(mesh_name)
    if not mesh:
        mesh = bpy.data.meshes.new(mesh_name)
    else:
        mesh.clear_geometry() # AI Editor Note: Force clear to ensure correct orientation update
    
    bm = bmesh.new()
        
    # AI Editor Note: Tip at Origin (0,0,0) to anchor head to vertex.
    v_tip = bm.verts.new((0, 0, 0))
    # Tail at (0,0,1) - Points away from vertex
    v_tail = bm.verts.new((0, 0, 1))
    
    # Arrowhead
    w = 0.15
    z_base = 0.3 # Base is 0.3 units from tip
    v1 = bm.verts.new((w, w, z_base))
    v2 = bm.verts.new((-w, w, z_base))
    v3 = bm.verts.new((-w, -w, z_base))
    v4 = bm.verts.new((w, -w, z_base))
    
    bm.edges.new((v_tip, v_tail))
    bm.edges.new((v_tip, v1))
    bm.edges.new((v_tip, v2))
    bm.edges.new((v_tip, v3))
    bm.edges.new((v_tip, v4))
    bm.edges.new((v1, v2))
    bm.edges.new((v2, v3))
    bm.edges.new((v3, v4))
    bm.edges.new((v4, v1))
    
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def update_arrow_settings(self, context):
    """Updates the size and scale of dimension arrows for ALL dimension objects in the scene."""
    # AI Editor Note: Direction map for rotation calculation
    direction_map = {
        'X': mathutils.Vector((1, 0, 0)),
        'Y': mathutils.Vector((0, 1, 0)),
        'Z': mathutils.Vector((0, 0, 1)),
        '-X': mathutils.Vector((-1, 0, 0)),
        '-Y': mathutils.Vector((0, -1, 0)),
        '-Z': mathutils.Vector((0, 0, -1)),
    }

    arrow_s = context.scene.urdf_dim_arrow_scale
    text_s = context.scene.urdf_dim_text_scale

    for obj in context.scene.objects:
        if obj.get("urdf_is_dimension"):
            # AI Editor Note: Get direction from the object itself, allowing per-dimension settings.
            # Fallback to 'Z' if not set (e.g. old files).
            dir_enum = getattr(obj, "urdf_dim_direction", 'Z')
            target_vec = direction_map.get(dir_enum, mathutils.Vector((0, 0, 1)))
            
            rot_quat = target_vec.to_track_quat('Z', 'Y')
            rot_euler = rot_quat.to_euler()

            arrows = []
            # 1. Check direct constraints (Normal mode)
            for c in obj.constraints:
                if c.type == 'COPY_LOCATION' and c.target and "Dim_Arrow" in c.target.name:
                    arrows.append(c.target)
            
            # 2. Check parent constraints (Placement mode)
            if not arrows and obj.parent and obj.parent.name.startswith("Anchor_"):
                for c in obj.parent.constraints:
                    if c.type == 'COPY_LOCATION' and c.target and "Dim_Arrow" in c.target.name:
                        arrows.append(c.target)
            
            # AI Editor Note: Determine old arrow scale from existing arrows before updating them.
            old_arrow_s = arrow_s
            if arrows:
                if arrows[0].type == 'EMPTY':
                    old_arrow_s = arrows[0].empty_display_size
                else:
                    old_arrow_s = arrows[0].scale[0]

            # AI Editor Note: Update Text Scale
            obj.scale = (text_s, text_s, text_s)

            # AI Editor Note: Smart Position Update based on Arrow Scale Delta.
            if abs(old_arrow_s - arrow_s) > 0.0001:
                # Scale changed: Apply delta movement along the arrow axis
                obj.location += target_vec * (arrow_s - old_arrow_s)
            elif not getattr(obj, "urdf_dim_is_manual", False):
                # No scale change and not manual: Snap to default position
                obj.location = target_vec * arrow_s

            for arrow in arrows:
                # AI Editor Note: Use scale property to control visual size of the Empty.
                if arrow.type == 'EMPTY':
                    arrow.empty_display_size = arrow_s
                else:
                    arrow.scale = (arrow_s, arrow_s, arrow_s)
                # AI Editor Note: Set location to (0,0,0) so Origin is at the Vertex.
                # This allows for easy scaling from the vertex anchor point.
                # AI Editor Note: Only reset if using Vertex parenting (Legacy/Deforming).
                # For static vertex mode (Object parent), we must preserve the offset.
                if arrow.parent_type == 'VERTEX':
                    arrow.location = (0, 0, 0)
                # AI Editor Note: Update rotation to match direction setting
                arrow.rotation_euler = rot_euler

class URDF_OT_AddTextDescription(bpy.types.Operator):
    """Add a text description label to the selected element"""
    bl_idname = "urdf.add_text_description"
    bl_label = "Add Text Description"
    bl_options = {'REGISTER', 'UNDO'}

    text: bpy.props.StringProperty(name="Description", default="Label")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.active_object
        location = obj.matrix_world.translation.copy()
        parent_args = {}
        original_mode = context.mode

        if context.mode == 'EDIT_MESH' and obj.type == 'MESH':
            bm = bmesh.from_edit_mesh(obj.data)
            selected_verts = [v for v in bm.verts if v.select]
            if selected_verts:
                target_v = selected_verts[-1]
                location = obj.matrix_world @ target_v.co
                parent_args = {'parent': obj, 'parent_type': 'VERTEX', 'parent_vertices': (target_v.index, 0, 0)}
            else:
                self.report({'WARNING'}, "No vertices selected")
                return {'CANCELLED'}
            bpy.ops.object.mode_set(mode='OBJECT')
        elif context.mode == 'OBJECT':
             parent_args = {'parent': obj, 'parent_type': 'OBJECT'}

        # Create Text Object
        font_curve = bpy.data.curves.new(type="FONT", name="Description_Curve")
        font_curve.body = self.text
        font_curve.align_x = 'CENTER'
        font_curve.align_y = 'CENTER'
        
        text_obj = bpy.data.objects.new(name="Description_Text", object_data=font_curve)
        
        coll = bpy.data.collections.get("URDF_Dimensions")
        if not coll:
            coll = bpy.data.collections.new("URDF_Dimensions")
            context.scene.collection.children.link(coll)
        coll.objects.link(text_obj)
        
        text_obj.location = location
        text_obj.scale = (0.2, 0.2, 0.2)
        text_obj.show_in_front = True # Always visible (X-Ray)

        # Assign Material
        mat = get_or_create_text_material(context)
        if text_obj.data.materials:
            text_obj.data.materials[0] = mat
        else:
            text_obj.data.materials.append(mat)

        if parent_args:
            text_obj.parent = parent_args['parent']
            text_obj.parent_type = parent_args['parent_type']
            if 'parent_vertices' in parent_args:
                text_obj.parent_vertices = parent_args['parent_vertices']
                text_obj.location = (0,0,0)

        if context.scene.camera:
            c = text_obj.constraints.new('DAMPED_TRACK')
            c.target = context.scene.camera
            c.track_axis = 'TRACK_Z'
        
        if original_mode == 'EDIT_MESH':
             context.view_layer.objects.active = obj
             bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}

class URDF_OT_RemoveDimension(bpy.types.Operator):
    """Removes the selected dimension and its associated arrows/anchors"""
    bl_idname = "urdf.remove_dimension"
    bl_label = "Remove Dimension"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.get("urdf_is_dimension")

    def execute(self, context):
        text_obj = context.active_object
        objects_to_delete = {text_obj}
        
        # Find Anchor
        anchor = text_obj.parent
        if anchor:
            objects_to_delete.add(anchor)
            
            # Find Arrows from Anchor constraints
            for c in anchor.constraints:
                if c.type == 'COPY_LOCATION' and c.target:
                    objects_to_delete.add(c.target)
        
        # Delete objects
        for obj in objects_to_delete:
            if obj.name in context.scene.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            
        self.report({'INFO'}, "Dimension removed.")
        return {'FINISHED'}

class URDF_OT_AddDimension(bpy.types.Operator):
    """Generate a dimension measurement between selected elements"""
    bl_idname = "urdf.add_dimension"
    bl_label = "Add Dimension (Vertex to Vertex)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        scene = context.scene
        unit_settings = scene.unit_settings
        
        start_loc = None
        end_loc = None
        
        # Parenting info: (Object, Type, Bone/VertexIndex)
        parent_info_a = None
        parent_info_b = None
        
        original_mode = context.mode

        if context.mode == 'OBJECT':
            sel = context.selected_objects
            if len(sel) != 2:
                self.report({'WARNING'}, "Select exactly 2 objects in Object Mode.")
                return {'CANCELLED'}
            
            obj_a = sel[0]
            obj_b = sel[1]
            start_loc = obj_a.matrix_world.translation
            end_loc = obj_b.matrix_world.translation
            
            parent_info_a = (obj_a, 'OBJECT', None)
            parent_info_b = (obj_b, 'OBJECT', None)
            
        elif context.mode == 'EDIT_MESH':
            obj = context.active_object
            bm = bmesh.from_edit_mesh(obj.data)
            verts = [v for v in bm.verts if v.select]
            
            if len(verts) == 2:
                v1, v2 = verts
            elif len(verts) > 2:
                 # Check edges
                 edges = [e for e in bm.edges if e.select]
                 if len(edges) == 1:
                     v1 = edges[0].verts[0]
                     v2 = edges[0].verts[1]
                 else:
                     self.report({'WARNING'}, "Select exactly 2 vertices or 1 edge.")
                     return {'CANCELLED'}
            else:
                self.report({'WARNING'}, "Select exactly 2 vertices or 1 edge.")
                return {'CANCELLED'}
            
            start_loc = obj.matrix_world @ v1.co
            end_loc = obj.matrix_world @ v2.co
            
            parent_info_a = (obj, 'VERTEX', v1.index)
            parent_info_b = (obj, 'VERTEX', v2.index)
            
            # Switch to Object mode to create objects
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
             self.report({'WARNING'}, "Mode not supported.")
             return {'CANCELLED'}

        # Create Collection
        coll = bpy.data.collections.get("URDF_Dimensions")
        if not coll:
            coll = bpy.data.collections.new("URDF_Dimensions")
            context.scene.collection.children.link(coll)
            
        # Create Arrow A (Start) - Mesh Object
        # AI Editor Note: Use wire mesh with origin at tip for better control.
        arrow_mesh = create_arrow_mesh_data()
        ea = bpy.data.objects.new("Dim_Arrow_A", arrow_mesh)
        ea.scale = (scene.urdf_dim_arrow_scale, scene.urdf_dim_arrow_scale, scene.urdf_dim_arrow_scale)
        coll.objects.link(ea)
        
        # Create Arrow B (End) - Mesh Object
        eb = bpy.data.objects.new("Dim_Arrow_B", arrow_mesh)
        eb.scale = (scene.urdf_dim_arrow_scale, scene.urdf_dim_arrow_scale, scene.urdf_dim_arrow_scale)
        coll.objects.link(eb)
        
        # Parenting
        if parent_info_a:
            p_obj, p_type, p_sub = parent_info_a
            ea.parent = p_obj
            if p_type == 'VERTEX':
                ea.parent_type = 'VERTEX'
                ea.parent_vertices = (p_sub, 0, 0)
        else:
            ea.location = start_loc
        
        if parent_info_b:
            p_obj, p_type, p_sub = parent_info_b
            eb.parent = p_obj
            if p_type == 'VERTEX':
                eb.parent_type = 'VERTEX'
                eb.parent_vertices = (p_sub, 0, 0)
        else:
            eb.location = end_loc

        # --- Arrow Orientation ---
        # AI Editor Note: Mesh is now Tip at Origin (0,0,0), Tail at (0,0,1).
        # To point Tail along +Z, we align +Z to +Z.
        direction_map = {
            'X': mathutils.Vector((1, 0, 0)),
            'Y': mathutils.Vector((0, 1, 0)),
            'Z': mathutils.Vector((0, 0, 1)),
            '-X': mathutils.Vector((-1, 0, 0)),
            '-Y': mathutils.Vector((0, -1, 0)),
            '-Z': mathutils.Vector((0, 0, -1)),
        }
        
        target_vec = direction_map.get(context.scene.urdf_dim_direction, mathutils.Vector((0, 0, 1)))
        
        # Calculate rotation to align Local Z with target_vec
        rot_quat = target_vec.to_track_quat('Z', 'Y')
        rot_euler = rot_quat.to_euler()
        
        ea.rotation_euler = rot_euler
        eb.rotation_euler = rot_euler
        
        # AI Editor Note: Location is already set correctly during parenting.
        # Do not reset to (0,0,0) as that would lose the vertex offset.
        
        # --- Create Dynamic Text (Mesh + GN) ---
        # We use a mesh object to host the Geometry Nodes modifier
        txt_mesh = bpy.data.meshes.new("Dim_Text_Mesh")
        txt_obj = bpy.data.objects.new("Dim_Label", txt_mesh)
        coll.objects.link(txt_obj)
        txt_obj.show_in_front = True # Always visible (X-Ray)
        
        # Assign Material
        mat = get_or_create_text_material(context)
        if txt_obj.data.materials:
            txt_obj.data.materials[0] = mat
        else:
            txt_obj.data.materials.append(mat)
        
        # --- Create Anchor for Text ---
        # AI Editor Note: Use an anchor Empty to hold the location constraints.
        # This allows the text object to be moved locally (G) without fighting constraints.
        anchor = bpy.data.objects.new(f"Anchor_{txt_obj.name}", None)
        anchor.empty_display_type = 'PLAIN_AXES'
        anchor.empty_display_size = 0.1
        coll.objects.link(anchor)
        
        # Constrain Anchor to midpoint
        # AI Editor Note: Correct midpoint logic: Move to A (100%), then 50% towards B.
        c = anchor.constraints.new('COPY_LOCATION')
        c.target = ea
        c.influence = 1.0
        c = anchor.constraints.new('COPY_LOCATION')
        c.target = eb
        c.influence = 0.5
        
        # Parent Text to Anchor
        txt_obj.parent = anchor
        # AI Editor Note: Apply initial scale
        arrow_s = scene.urdf_dim_arrow_scale
        text_s = scene.urdf_dim_text_scale
        txt_obj.scale = (text_s, text_s, text_s)
        # AI Editor Note: Offset text to align with arrow tails.
        # This places the text "in the middle" of the bracket formed by the arrows (at the tails).
        txt_obj.location = target_vec * arrow_s

        # Align Text to Creation Axis (Flat 2D Plane)
        txt_obj.rotation_euler = rot_euler
            
        # --- Setup Geometry Nodes for Dynamic Text ---
        setup_dimension_gn(txt_obj, ea, eb, context)
        
        # AI Editor Note: Add driver for Object Scale to GN modifier.
        # This ensures the displayed dimension is compensated for the object's scale.
        # FIX: Use socket identifier instead of name for driver path.
        mod = txt_obj.modifiers.get("Dynamic_Dimension")
        if mod and mod.node_group and mod.node_group.interface:
            sock = mod.node_group.interface.items_tree.get("Object Scale")
            if sock:
                create_driver(txt_obj, 'scale[0]', "Dynamic_Dimension", sock.identifier)

        # Configure Units for GN
        # Mark as dimension for updates and trigger initial update
        txt_obj["urdf_is_dimension"] = True
        # AI Editor Note: Initialize object direction from scene default
        txt_obj.urdf_dim_direction = context.scene.urdf_dim_direction
        
        txt_obj.urdf_dim_is_manual = False # Initialize as auto-placed
        update_dimensions(context.scene)
        
        # Restore Edit Mode if needed
        if original_mode == 'EDIT_MESH':
             bpy.ops.object.mode_set(mode='EDIT')
             
        self.report({'INFO'}, "Added dynamic dimension.")
        return {'FINISHED'}

class OPS_OT_AddModifier(bpy.types.Operator):
    bl_idname = "urdf.add_parametric_mod"
    bl_label = "Add Parametric Feature"
    bl_options = {'REGISTER', 'UNDO'}
    type: bpy.props.EnumProperty(items=[('BEVEL', "Fillet/Chamfer", ""), ('SOLIDIFY', "Shell/Thicken", ""), ('SCREW', "Revolve", ""), ('MIRROR', "Mirror", "")])
    
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        
        if self.type == 'BEVEL':
            mod = obj.modifiers.new(f"{MOD_PREFIX}Parametric_Fillet", 'BEVEL')
            mod.limit_method = 'ANGLE'
            mod.angle_limit = math.radians(30)
            mod.harden_normals = True
        elif self.type == 'SOLIDIFY':
            # --- Create the Solidify modifier for the shell effect ---
            mod = obj.modifiers.new(f"{MOD_PREFIX}Parametric_Shell", 'SOLIDIFY')
            
            # --- Set offset to 1 for an outward shell ---
            # The default is -1 (inward), but an outward shell is often more predictable
            # for mechanical parts, preventing self-intersection with internal geometry.
            mod.offset = 1.0

            # --- Calculate a sensible default thickness based on object size ---
            # Set the thickness to 10% of the object's average dimension.
            # This provides a reasonable starting point relative to the object's scale.
            avg_dimension = (obj.dimensions.x + obj.dimensions.y + obj.dimensions.z) / 3.0 if obj.dimensions.length > 0 else 1.0
            mod.thickness = avg_dimension * 0.1
        elif self.type == 'SCREW':
            obj.modifiers.new(f"{MOD_PREFIX}Parametric_Revolve", 'SCREW')
        elif self.type == 'MIRROR':
            obj.modifiers.new(f"{MOD_PREFIX}Parametric_Mirror", 'MIRROR')
            
        self.report({'INFO'}, f"Added {self.type.lower()} modifier to '{obj.name}'.")
        return {'FINISHED'}

class OPS_OT_AddSimplify(bpy.types.Operator):
    """Applies geometry cleanup operations (Weld or Simplify) directly to the mesh"""
    bl_idname = "urdf.add_simplify"
    bl_label = "Simplify"
    bl_options = {'REGISTER', 'UNDO'}
    
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[
            ('WELD', "Weld (Merge)", "Merge vertices by distance to fix broken lines"),
            ('COLLAPSE', "Decimate (Simplify)", "Reduce vertex count globally"),
            ('QUADIFY', "Quad-ify", "Convert triangles to quads"),
        ],
        default='WELD'
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        original_mode = obj.mode
        
        # --- AI Editor Note: Handle Multi-Object Editing ---
        # Collect objects to process based on context.
        objects_to_process = [obj]
        if context.mode == 'OBJECT':
            objects_to_process = [o for o in context.selected_objects if o.type == 'MESH']

        if self.mode == 'WELD':
            for target_obj in objects_to_process:
                context.view_layer.objects.active = target_obj
                
                # 1. Destructive Intersect (Create vertices at overlaps)
                # This fulfills the requirement to "create new vertices in between overlapping edges".
                if target_obj.mode != 'EDIT':
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                
                # AI Editor Note: Use EXACT solver for precise cuts at intersections
                bpy.ops.mesh.intersect(mode='SELECT', solver='EXACT')
                
                # --- AI Editor Note: Auto Merge & Split Edges ---
                # Enable Auto Merge and Split Edges & Faces to handle vertices on edges.
                # This ensures that vertices lying on edges split the edge, creating valid topology.
                context.tool_settings.use_mesh_automerge = True
                context.tool_settings.use_mesh_automerge_and_split = True
                
                # Trigger the auto-merge logic by performing a zero-distance translation.
                # This forces Blender to process the geometry with the enabled settings.
                bpy.ops.transform.translate(value=(0, 0, 0))
                
                if original_mode == 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                
                # 2. Non-Destructive Weld (Merge vertices)
                # Adds the requested Weld modifier to handle the merging.
                if f"{MOD_PREFIX}Weld" not in target_obj.modifiers:
                    mod = target_obj.modifiers.new(f"{MOD_PREFIX}Weld", 'WELD')
                    mod.merge_threshold = 0.001
            
            self.report({'INFO'}, "Applied Intersect, Auto-Merge & Added Weld Modifier")

        elif self.mode == 'COLLAPSE':
            for target_obj in objects_to_process:
                # AI Editor Note: Use Decimate Modifier for non-destructive reduction
                mod_name = f"{MOD_PREFIX}Decimate"
                mod = target_obj.modifiers.get(mod_name)
                if not mod:
                    mod = target_obj.modifiers.new(mod_name, 'DECIMATE')
                
                # AI Editor Note: Switch to Planar (Dissolve) mode for maximum simplification while retaining shape
                mod.decimate_type = 'DISSOLVE'
                mod.angle_limit = math.radians(20.0) # Increased to catch subdivided flat faces reliably
                mod.use_dissolve_boundaries = True # Ensure grid topology on flat faces is cleaned up
            self.report({'INFO'}, "Applied Decimate Modifier (Planar)")

        elif self.mode == 'QUADIFY':
            for target_obj in objects_to_process:
                context.view_layer.objects.active = target_obj
                # Ensure Edit Mode for mesh operation
                if target_obj.mode != 'EDIT':
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                
                bpy.ops.mesh.tris_convert_to_quads()
                
                if original_mode == 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            
            self.report({'INFO'}, "Converted Tris to Quads")

        # Restore original mode
        if original_mode == 'OBJECT' and context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=original_mode)
            
        return {'FINISHED'}

class OPS_OT_SetupLinearArray(bpy.types.Operator):
    bl_idname = "urdf.setup_linear_array"
    bl_label = "Linear Pattern"
    bl_options = {'REGISTER', 'UNDO'}
    
    count: bpy.props.IntProperty(name="Count", default=3, min=2)
    offset: bpy.props.FloatVectorProperty(name="Offset", default=(1.0, 0.0, 0.0), subtype='TRANSLATION')

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        
        base_name = f"{MOD_PREFIX}Linear_Pattern"
        mod_name = base_name
        i = 0
        while obj.modifiers.get(mod_name):
            i += 1
            mod_name = f"{base_name}.{i:03d}"

        mod = obj.modifiers.new(mod_name, 'ARRAY')
        mod.count = self.count
        # Default to relative offset for a non-destructive, scalable pattern.
        # Constant offset can be enabled manually by the user if absolute distances are needed.
        mod.use_relative_offset = True
        mod.use_constant_offset = False
        mod.relative_offset_displace = self.offset
        
        self.report({'INFO'}, f"Added linear array to '{obj.name}'.")
        return {'FINISHED'}

class OPS_OT_SetupRadialArray(bpy.types.Operator):
    bl_idname = "urdf.setup_radial_array"
    bl_label = "Radial Pattern"
    bl_options = {'REGISTER', 'UNDO'}
    count: bpy.props.IntProperty(default=6, min=2)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        
        # --- Create and configure the axis Empty ---
        # This empty object will act as the pivot point for the radial array.
        empty = bpy.data.objects.new(f"Radial_Axis_{obj.name}", None)
        context.collection.objects.link(empty)
        
        # Parent the empty to the object first. This ensures that all subsequent
        # transformations on the empty are in the object's local space.
        empty.parent = obj
        
        # Explicitly set the empty's local transform to the parent's origin (identity).
        # This guarantees it is perfectly centered and has no initial rotation or scale,
        # preventing unwanted offsets in the array that cause a screw pattern.
        empty.location = (0, 0, 0)
        empty.rotation_euler = (0, 0, 0)
        empty.scale = (1, 1, 1)
        
        # The empty's local rotation now determines the angle between array instances.
        empty.rotation_euler.z = (math.pi * 2) / self.count
        
        # --- Create and configure the Array modifier ---
        mod = obj.modifiers.new(f"{MOD_PREFIX}Radial_Array_{empty.name}", 'ARRAY')
        mod.count = self.count
        # Enable Relative Offset by default with a factor of 1.0 on the X-axis.
        # This creates a spiral pattern by default. For a flat radial pattern,
        # the user can set the relative offset to zero in the modifier panel.
        mod.use_relative_offset = True
        mod.relative_offset_displace = (1.0, 0.0, 0.0)
        
        # The primary control for the radial pattern is the Object Offset.
        # Because the empty is a child, its local transform is used as the offset.
        mod.use_object_offset = True
        mod.offset_object = empty
        
        self.report({'INFO'}, f"Added radial array to '{obj.name}'.")
        return {'FINISHED'}

class OPS_OT_CreateCurveForPath(bpy.types.Operator):
    """Creates a new curve object at the 3D cursor, ready for editing"""
    bl_idname = "urdf.create_curve_for_path"
    bl_label = "Create Path Curve"
    bl_options = {'REGISTER', 'UNDO'}

    type: bpy.props.EnumProperty(
        name="Curve Type",
        items=[
            ('BEZIER', "Bezier", "Create a Bezier curve"),
            ('NURBS', "NURBS", "Create a NURBS curve"),
            ('POLY', "Poly", "Create a Poly curve"),
        ],
        default='BEZIER'
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # Ensure we are in object mode before creating new objects
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Create curve data and object
        curve_data = bpy.data.curves.new("Path_Curve_Data", type='CURVE')
        curve_data.dimensions = '3D'
        
        spline = curve_data.splines.new(self.type)
        
        # --- MODIFICATION: Create single-vertex curves ---
        # Per user request, all curve types now start with a single vertex at the origin.
        # This provides a consistent starting point for extrusion.
        if self.type == 'BEZIER':
            # Configure the single, default bezier point.
            spline.bezier_points[0].co = (0, 0, 0)
            spline.bezier_points[0].handle_left_type = 'AUTO'
            spline.bezier_points[0].handle_right_type = 'AUTO'
        else: # POLY or NURBS
            # Create a single point. The user can then extrude from it.
            spline.points[0].co = (0, 0, 0, 1)

        path_obj = bpy.data.objects.new("Path_Curve", curve_data)
        path_obj.location = context.scene.cursor.location
        context.collection.objects.link(path_obj)

        # Make the new curve active and enter edit mode for immediate shaping
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = path_obj
        path_obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Select the last created point for immediate extrusion by the user.
        bpy.ops.curve.select_all(action='DESELECT')
        spline = path_obj.data.splines[0]
        if spline.type == 'BEZIER':
            # For Bezier, select the last point's control point
            if len(spline.bezier_points) > 0:
                spline.bezier_points[-1].select_control_point = True
        elif spline.points: # For NURBS/POLY
            if len(spline.points) > 0:
                spline.points[-1].select = True

        self.report({'INFO'}, f"Created new {self.type} curve '{path_obj.name}' at cursor.")
        return {'FINISHED'}

class OPS_OT_SetupCurveArray(bpy.types.Operator):
    """Creates an array of the selected object(s) that follows the active curve"""
    bl_idname = "urdf.setup_curve_array"
    bl_label = "Follow Curve"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        name="Array Type",
        description="Choose how the array follows the curve",
        items=[
            ('DEFORM', "Deform", "Stretches and bends the mesh to fit the curve. Good for flexible parts like hoses."),
            ('RIGID', "Rigid Instances Array", "Creates rigid, non-deforming copies along the curve. Good for chains or treads."),
        ],
        default='DEFORM'
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'CURVE':
            cls.poll_message_set("Active object must be a Curve.")
            return False

        selected_meshes = [obj for obj in context.selected_objects if obj != active_obj and obj.type == 'MESH']

        if not selected_meshes:
            cls.poll_message_set("Select a mesh object to array, then the curve object last.")
            return False

        for mesh_obj in selected_meshes:
            # AI Editor Note: Allow parametric parts to be used with this tool, but explicitly
            # block 'CHAIN' types, as they have their own dedicated curve-following system.
            # This allows users to create arrays of gears, custom links, etc., along a curve.
            if hasattr(mesh_obj, 'urdf_mech_props') and mesh_obj.urdf_mech_props.is_part:
                if mesh_obj.urdf_mech_props.category == 'CHAIN':
                    cls.poll_message_set("Cannot use 'Follow Curve' on a Chain part. Use its own settings.")
                    return False
        
        return True

    def execute(self, context: bpy.types.Context) -> Set[str]:
        path_obj = context.active_object  # The active object is the curve path
        objects_to_modify = [obj for obj in context.selected_objects if obj != path_obj and obj.type == 'MESH']

        # --- Main loop to apply the selected mode to each object ---
        for obj in objects_to_modify:
            
            # --- STEP 1: Clean up any previous setups from this tool ---
            # This ensures that switching between modes or re-running the operator works cleanly.

            # A. Remove modifiers created by this tool on the main object.
            for mod_name in [f"{MOD_PREFIX}FollowCurve_Array", f"{MOD_PREFIX}FollowCurve_Deform"]:
                if mod_name in obj.modifiers:
                    obj.modifiers.remove(obj.modifiers[mod_name])

            # B. If the object was part of a 'Rigid' setup, dismantle it completely.
            # Use startswith for robustness in case of .001 suffixes.
            proxy_name_prefix = f"Proxy_{obj.name}"
            if obj.parent and obj.parent.name.startswith(proxy_name_prefix):
                proxy_obj = obj.parent
                
                # Restore object's world transform before unparenting.
                original_matrix = obj.matrix_world.copy()
                obj.parent = None
                obj.matrix_world = original_matrix
                
                # Delete the old proxy object and its mesh data to prevent orphans.
                if proxy_obj.data:
                    bpy.data.meshes.remove(proxy_obj.data, do_unlink=True)
                bpy.data.objects.remove(proxy_obj, do_unlink=True)

            # C. Ensure the object is visible and selectable again.
            obj.hide_set(False)
            obj.hide_select = False
            obj.hide_viewport = False
            obj.hide_render = False

            # --- STEP 2: Apply the new setup based on the selected mode ---

            if self.mode == 'DEFORM':
                # --- Deforming Array Method ---

                # --- FIX: Auto-align object to curve start ---
                # To prevent the object from jumping when the Curve modifier is added,
                # its origin must be aligned with the starting point of the curve.
                # This code block calculates the world-space position of the curve's
                # first vertex and moves the object there before adding modifiers.
                if path_obj.data.splines:
                    spline = path_obj.data.splines[0]
                    if spline.type == 'BEZIER' and spline.bezier_points:
                        first_vtx_local_co = spline.bezier_points[0].co
                    elif spline.points:
                        first_vtx_local_co = spline.points[0].co.to_3d()
                    else:
                        # Fallback for empty curves: use the curve object's origin.
                        first_vtx_local_co = mathutils.Vector((0,0,0))
                    
                    # Move the object's origin to the curve's starting point.
                    obj.matrix_world.translation = path_obj.matrix_world @ first_vtx_local_co

                # This is the classic setup that bends and stretches the mesh itself.
                # It requires the object to have enough geometry to deform smoothly.
                array_mod = obj.modifiers.new(f"{MOD_PREFIX}FollowCurve_Array", 'ARRAY')
                array_mod.fit_type = 'FIT_CURVE'
                array_mod.curve = path_obj
                array_mod.use_relative_offset = True
                array_mod.relative_offset_displace = (1.0, 0.0, 0.0)

                curve_mod = obj.modifiers.new(f"{MOD_PREFIX}FollowCurve_Deform", 'CURVE')
                curve_mod.object = path_obj
                curve_mod.deform_axis = 'POS_X'
            
            elif self.mode == 'RIGID':
                # --- NEW: Geometry Nodes Rigid Instancing Method ---
                # This modern approach uses a GN modifier on the curve itself.
                # It avoids parenting and hiding the original object, which resolves
                # the user's issue of the object being grayed out and hard to edit.
                # The original object remains visible and fully editable.
                
                # Get or create the reusable node group for this tool.
                gn_group = setup_gn_for_rigid_array(path_obj)
                
                # Add a dedicated GN modifier to the curve for this specific object.
                mod_name = f"{MOD_PREFIX}RigidArray_{obj.name}"
                if mod_name in path_obj.modifiers:
                    path_obj.modifiers.remove(path_obj.modifiers[mod_name])
                
                mod = path_obj.modifiers.new(name=mod_name, type='NODES')
                mod.node_group = gn_group
                
                # --- Connect Modifier Inputs ---
                iface = gn_group.interface
                instance_obj_socket = iface.items_tree.get("Instance Object")
                spacing_socket = iface.items_tree.get("Spacing")
                
                if instance_obj_socket:
                    mod[instance_obj_socket.identifier] = obj
                
                if spacing_socket:
                    # Use the object's X-dimension as the default spacing.
                    spacing = obj.dimensions.x if obj.dimensions.x > 0.01 else 1.0
                    mod[spacing_socket.identifier] = spacing

        self.report({'INFO'}, f"Set {len(objects_to_modify)} object(s) to follow '{path_obj.name}' using '{self.mode}' mode.")
        return {'FINISHED'}

class OPS_OT_SmartSmooth(bpy.types.Operator):
    bl_idname = "urdf.smart_smooth"
    bl_label = "Smart Smooth"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context: bpy.types.Context) -> Set[str]:
        obj = context.active_object
        
        # Apply the base auto smooth (Edge Split via GN)
        apply_auto_smooth(obj)
            
        if f"{MOD_PREFIX}Weighted_Normal" not in obj.modifiers:
            mod = obj.modifiers.new(f"{MOD_PREFIX}Weighted_Normal", 'WEIGHTED_NORMAL')
            mod.keep_sharp = True
            
        self.report({'INFO'}, f"Applied smart smooth to '{obj.name}'.")
        return {'FINISHED'}


class OPS_OT_CreatePart(bpy.types.Operator):
    bl_idname = "urdf.create_part"
    bl_label = "Generate"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context: bpy.types.Context) -> Set[str]:
        # --- AI Editor Note: Generation Logic ---
        # This operator follows a clear pattern for each part category:
        # 1. Calculate a scale factor based on the optional "Generation Size Cage".
        # 2. Create the necessary Blender object(s) (Mesh, Curve, Empties).
        # 3. Assign the addon's parametric properties (`URDF_MechProps`).
        # 4. Apply the scale factor to the default parametric values (e.g., radius, length).
        # 5. For complex parts (Spring, Chain), update helper objects and native properties.
        # 6. Call the appropriate generation/setup function (`regenerate_mech_mesh`, `setup_native_spring`, etc.).

        # --- 1. Get Scaling Factor from Generation Cage ---
        scale_factor = 0.1 # Default base dimension (10cm) if cage is unused
        use_cage = context.scene.urdf_use_generation_cage
        if use_cage:
            scale_factor = context.scene.urdf_generation_cage_size
            self.report({'INFO'}, f"Generating part with Size Cage: {scale_factor:.3f}m")
        else:
            self.report({'INFO'}, f"Generating part with Default Size: {scale_factor:.3f}m")

        cursor_loc = context.scene.cursor.location
        cat = context.scene.urdf_part_category
        type_sub = context.scene.urdf_part_type
        
        # --- AI Editor Note: Use the new centralized helper function ---
        new_obj = create_parametric_part_object(context, cat, type_sub, cursor_loc, scale_factor)
        props = new_obj.urdf_mech_props

        # --- AI Editor Note: Auto-rigging for Basic Robot Joints ---
        # Moved outside the removed 'if' block to ensure it runs.
        if cat == 'BASIC_JOINT':
            rig = ensure_default_rig(context)
            if not rig:
                self.report({'ERROR'}, "Could not find or create a default rig.")
                return {'CANCELLED'}
            
            # AI Editor Note: Use the shared helper function for rigging basic joints.
            # This ensures consistency between manual creation and AI generation.
            base_bone, joint_bone = rig_parametric_joint(context, new_obj)
            
            if joint_bone:
                pbone_joint = rig.pose.bones.get(joint_bone)

                # Sync to UI tool
                core._joint_editor_update_guard = True
                try:
                    tool_props = context.scene.urdf_joint_editor_settings
                    tool_props.joint_type = pbone_joint.urdf_props.joint_type
                    tool_props.axis_enum = pbone_joint.urdf_props.axis_enum
                    tool_props.joint_radius = pbone_joint.urdf_props.joint_radius
                    tool_props.lower_limit = pbone_joint.urdf_props.lower_limit
                    tool_props.upper_limit = pbone_joint.urdf_props.upper_limit
                finally:
                    core._joint_editor_update_guard = False

        if new_obj:
            # --- Set up initial viewport material ---
            # This ensures the new part has the correct default color immediately.
            # The update callback on the color property will handle subsequent changes.
            obj_for_material = new_obj
            props_owner = new_obj.urdf_mech_props

            if props_owner.category == 'CHAIN':
                # For chains, the material goes on the instanced link object,
                # but the properties are on the main curve object.
                obj_for_material = props_owner.instanced_link_obj
            
            if obj_for_material and hasattr(props_owner, 'material'):
                # Use the color from the main properties owner (the curve for chains).
                setup_and_update_material(obj_for_material, props_owner.material.color)

            for o in context.view_layer.objects.selected:
                o.select_set(False)
            new_obj.select_set(True)
            context.view_layer.objects.active = new_obj
            self.report({'INFO'}, f"Created new part: {new_obj.name}")

        return {'FINISHED'}

class OPS_OT_ChainAddWrapObject(bpy.types.Operator):
    bl_idname = "urdf.chain_add_wrap_object"
    bl_label = "Add Wrap Object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        # Operator works on an active Chain object
        if not (obj and obj.urdf_mech_props.category == 'CHAIN'):
            return False
        # Ensure there is a selected object to wrap around
        selected = [o for o in context.selected_objects if o != obj]
        if not selected:
            return False
        return True

    def execute(self, context: bpy.types.Context) -> Set[str]:
        chain_obj = context.active_object
        props = chain_obj.urdf_mech_props
        targets = [o for o in context.selected_objects if o != chain_obj]

        # 1. Get or Create the Wrap Collection
        coll_name = f"URDF_Wraps_{chain_obj.name}"
        wrap_coll = bpy.data.collections.get(coll_name)
        if not wrap_coll:
            wrap_coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(wrap_coll)
        
        props.chain_wrap_collection = wrap_coll

        # 2. Add objects to collection and UI list
        for target in targets:
            # Check if already in list
            exists = False
            for item in props.chain_wrap_items:
                if item.target == target:
                    exists = True
                    break
            
            if not exists:
                # Link to collection if not already there
                if target.name not in wrap_coll.objects:
                    wrap_coll.objects.link(target)
                
                # Add to UI list
                item = props.chain_wrap_items.add()
                item.target = target

        # 3. Update GN Modifier
        mod_name = f"{MOD_PREFIX}Native_{props.type_chain.capitalize()}Chain"
        mod = chain_obj.modifiers.get(mod_name)
        if mod:
            # We need to find the socket index or name for "Wrap Collection"
            # Since we added it to the node group, it should be available.
            # We can access it by identifier if we knew it, or by name.
            # The setup_native_chain_gn function sets it up, but we can re-trigger it or set it here.
            # Re-running setup is safe.
            setup_native_wrap_gn(chain_obj)

        self.report({'INFO'}, f"Added {len(targets)} wrap objects to '{chain_obj.name}'")
        return {'FINISHED'}

class URDF_OT_SlinkyAddHook(bpy.types.Operator):
    """Adds a new middle hook for the Slinky spring at the 3D cursor location."""
    bl_idname = "urdf.slinky_add_hook"
    bl_label = "Add Middle Hook"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.urdf_mech_props.category == 'SPRING' and obj.urdf_mech_props.type_spring == 'SPRING_SLINKY'

    def execute(self, context):
        obj = context.active_object
        props = obj.urdf_mech_props
        
        # Create an Empty at the 3D cursor
        hook = bpy.data.objects.new(name=f"Hook_{obj.name}", object_data=None)
        hook.location = context.scene.cursor.location
        context.collection.objects.link(hook)
        hook.empty_display_type = 'SPHERE'
        hook.empty_display_size = 0.02
        
        # Add to collection
        item = props.slinky_hooks.add()
        item.target = hook
        
        # Trigger regeneration
        from .core import setup_native_slinky
        setup_native_slinky(obj, props.spring_start_obj, props.spring_end_obj)
        
        return {'FINISHED'}

class URDF_OT_SlinkyRemoveHook(bpy.types.Operator):
    """Removes the active middle hook from the Slinky spring."""
    bl_idname = "urdf.slinky_remove_hook"
    bl_label = "Remove Active Hook"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not (obj and obj.urdf_mech_props.category == 'SPRING'): return False
        return len(obj.urdf_mech_props.slinky_hooks) > 0

    def execute(self, context):
        obj = context.active_object
        props = obj.urdf_mech_props
        
        if props.slinky_active_index >= 0 and props.slinky_active_index < len(props.slinky_hooks):
            props.slinky_hooks.remove(props.slinky_active_index)
            props.slinky_active_index = max(0, props.slinky_active_index - 1)
            
            # Trigger regeneration
            from .core import setup_native_slinky
            setup_native_slinky(obj, props.spring_start_obj, props.spring_end_obj)
            
        return {'FINISHED'}

class OPS_OT_CreateElectronicPart(bpy.types.Operator):
    """Creates a new parametric electronic component."""
    bl_idname = "urdf.create_electronic_part"
    bl_label = "Generate Electronic Part"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        cursor_loc = context.scene.cursor.location
        type_sub = context.scene.urdf_electronics_type
        
        # --- 1. Get Scaling Factor from Generation Cage ---
        scale_factor = 0.1 # Default base dimension (10cm) if cage is unused
        if context.scene.urdf_use_generation_cage:
            scale_factor = context.scene.urdf_generation_cage_size
            self.report({'INFO'}, f"Generating part with Size Cage: {scale_factor:.3f}m")
        else:
            self.report({'INFO'}, f"Generating part with Default Size: {scale_factor:.3f}m")

        # Use the centralized helper
        new_obj = create_parametric_part_object(context, 'ELECTRONICS', type_sub, cursor_loc, scale_factor)
        props = new_obj.urdf_mech_props
        
        setup_and_update_material(new_obj, props.material.color)

        for o in context.view_layer.objects.selected:
            o.select_set(False)
        new_obj.select_set(True)
        context.view_layer.objects.active = new_obj
        self.report({'INFO'}, f"Created new electronic part: {new_obj.name}")

        return {'FINISHED'}

class OPS_OT_ChainAddPickedWrapObject(bpy.types.Operator):
    """Adds the object selected in the 'Pick Object' field to the wrap bundle"""
    bl_idname = "urdf.chain_add_picked_wrap_object"
    bl_label = "Add Picked Object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return (obj and obj.urdf_mech_props.category == 'CHAIN' and 
                obj.urdf_mech_props.wrap_picker is not None)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        chain_obj = context.active_object
        props = chain_obj.urdf_mech_props
        target = props.wrap_picker

        if not target:
            return {'CANCELLED'}

        # Reuse logic to ensure collection exists
        coll_name = f"URDF_Wraps_{chain_obj.name}"
        wrap_coll = bpy.data.collections.get(coll_name)
        if not wrap_coll:
            wrap_coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(wrap_coll)
        props.chain_wrap_collection = wrap_coll

        # Add to collection and list if not present
        if target.name not in wrap_coll.objects:
            wrap_coll.objects.link(target)
        
        if not any(item.target == target for item in props.chain_wrap_items):
            item = props.chain_wrap_items.add()
            item.target = target
            
        # Update GN and clear picker
        setup_native_wrap_gn(chain_obj)
        props.wrap_picker = None
        
        self.report({'INFO'}, f"Added '{target.name}' to wrap bundle.")
        return {'FINISHED'}

class OPS_OT_ChainRemoveWrapObject(bpy.types.Operator):
    bl_idname = "urdf.chain_remove_wrap_object"
    bl_label = "Remove Wrap Object"
    bl_options = {'REGISTER', 'UNDO'}
    
    index: bpy.props.IntProperty()

    def execute(self, context: bpy.types.Context) -> Set[str]:
        chain_obj = context.active_object
        if not chain_obj:
            return {'CANCELLED'}

        props = chain_obj.urdf_mech_props
        if not props.chain_wrap_items or self.index >= len(props.chain_wrap_items):
            return {'CANCELLED'}

        item = props.chain_wrap_items[self.index]
        target = item.target
        
        # Remove from collection
        if props.chain_wrap_collection and target and target.name in props.chain_wrap_collection.objects:
            props.chain_wrap_collection.objects.unlink(target)

        # Remove the item from the UI list.
        props.chain_wrap_items.remove(self.index)

        self.report({'INFO'}, f"Removed wrap object '{target.name if target else 'unknown'}'")
        return {'FINISHED'}

class OPS_OT_CalculateRatio(bpy.types.Operator):
    bl_idname = "urdf.calculate_ratio"
    bl_label = "Calculate Ratio"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for bone in bones_to_process:
            if not bone: continue
            props = bone.urdf_props
            target_name = props.ratio_ref_bone if props.ratio_ref_bone else props.ratio_target_bone
            if not target_name:
                continue
            target = bone.id_data.pose.bones.get(target_name)
            if target:
                is_rot_self = props.joint_type in ['revolute', 'continuous']
                is_rot_tgt = target.urdf_props.joint_type in ['revolute', 'continuous']
                
                # --- NEW: Use joint_radius for rotational joints (gears) and bone length for linear joints (racks) ---
                # This provides physically-based ratio calculation.
                
                # Determine the effective "length" or "radius" for the source (driver) bone
                len_driver = target.length
                if is_rot_tgt:
                    # For gears, the ratio is based on radius
                    len_driver = target.urdf_props.joint_radius if target.urdf_props.joint_radius > 0.001 else 1.0

                # Determine the effective "length" or "radius" for the target (follower) bone
                len_follower = bone.length
                if is_rot_self:
                    # For gears, the ratio is based on radius
                    len_follower = bone.urdf_props.joint_radius if bone.urdf_props.joint_radius > 0.001 else 1.0

                if len_follower < 0.0001:
                    len_follower = 0.0001
                
                # --- Logic for different joint type combinations ---
                if is_rot_self and not is_rot_tgt: # Follower is ROT, Driver is LIN (e.g., Rack and Pinion)
                    bone.urdf_props.ratio_value = 1.0 / len_follower 
                elif not is_rot_self and is_rot_tgt: # Follower is LIN, Driver is ROT (e.g., Pinion and Rack)
                    bone.urdf_props.ratio_value = len_driver
                elif is_rot_self and is_rot_tgt: # Follower is ROT, Driver is ROT (e.g., two gears)
                    bone.urdf_props.ratio_value = len_driver / len_follower
                else: # Both are LIN
                    bone.urdf_props.ratio_value = 1.0
                count += 1
                
        self.report({'INFO'}, f"Calculated ratio for {count} bone(s).")
        return {'FINISHED'}

class OPS_OT_AddMimic(bpy.types.Operator):
    bl_idname = "urdf.add_mimic"
    bl_label = "Add / Update Driver"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for bone in bones_to_process:
            if not bone: continue
            props = bone.urdf_props
            driver_name = props.ratio_target_bone
            if not driver_name:
                continue
                
            core.add_native_driver_relation(bone, driver_name, props.ratio_value, props.ratio_invert)
            found = False
            for m in props.mimic_drivers: 
                if m.target_bone == driver_name:
                    m.ratio = props.ratio_value
                    found = True
            if not found:
                item = props.mimic_drivers.add()
                item.target_bone = driver_name
                item.ratio = props.ratio_value
            count += 1
            
        self.report({'INFO'}, f"Added mimic driver to {count} bone(s).")
        return {'FINISHED'}

class OPS_OT_RemoveMimic(bpy.types.Operator):
    bl_idname = "urdf.remove_mimic"
    bl_label = "Remove Gear"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for bone in bones_to_process:
            if not bone or self.index >= len(bone.urdf_props.mimic_drivers): 
                continue
                
            item = bone.urdf_props.mimic_drivers[self.index]
            if bone.id_data.animation_data and bone.id_data.animation_data.drivers:
                drivers = bone.id_data.animation_data.drivers
                for i in range(len(drivers)-1, -1, -1):
                    d = drivers[i]
                    for v in d.driver.variables:
                        if v.targets[0].bone_target == item.target_bone:
                            drivers.remove(d)
                            break
            bone.urdf_props.mimic_drivers.remove(self.index)
            count += 1
            
        self.report({'INFO'}, f"Removed mimic driver from {count} bone(s).")
        return {'FINISHED'}

class OPS_OT_ClearConfig(bpy.types.Operator):
    bl_idname = "urdf.clear_config"
    bl_label = "Clear Config"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for bone in bones_to_process:
            if not bone: continue
            props = bone.urdf_props

            # Setting joint_type to 'none' triggers update_gizmo_prop,
            # which handles gizmos, FK constraints, and IK limits.
            props.joint_type = 'none'
            
            # Clear remaining properties manually
            props.lower_limit = -90.0
            props.upper_limit = 90.0
            # Reset sizing properties to their defaults
            props.joint_radius = 0.5
            props.gizmo_radius = 0.1
            props.use_ratio = False
            props.ratio_value = 1.0
            props.ratio_invert = False
            props.ratio_target_bone = ""
            props.ratio_ref_bone = ""
            props.mimic_drivers.clear()

            if bone.id_data.animation_data: 
                drivers = bone.id_data.animation_data.drivers
                for i in range(len(drivers)-1, -1, -1):
                    d = drivers[i]
                    if d.data_path.startswith(f"pose.bones[\"{bone.name}\"]"):
                        drivers.remove(d)
            count += 1
            
        self.report({'INFO'}, f"Cleared configuration for {count} bone(s).")
        return {'FINISHED'}

class OPS_OT_ApplyBoneConstraints(bpy.types.Operator):
    bl_idname = "urdf.bone_constraints"
    bl_label = "Apply Config"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bones_to_process = context.selected_pose_bones if context.selected_pose_bones else [context.active_pose_bone]
        
        count = 0
        for bone in bones_to_process:
            if not bone: continue
            apply_native_constraints(bone)
            count += 1
            
        self.report({'INFO'}, f"Applied constraints to {count} bone(s).")
        return {'FINISHED'}

class OPS_OT_PickBone(bpy.types.Operator):
    bl_idname = "urdf.pick_bone"
    bl_label = "Pick Bone"
    mode: bpy.props.IntProperty(default=0)
    source_bone_name: bpy.props.StringProperty(name="Source Bone Name")
    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        if context.mode == 'POSE':
            self.source_bone_name = context.active_pose_bone.name
            context.window.cursor_set('EYEDROPPER')
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        return {'CANCELLED'}
    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> Set[str]:
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            bpy.ops.view3d.select(location=(event.mouse_region_x, event.mouse_region_y))
            if context.active_pose_bone and context.active_pose_bone.name != self.source_bone_name:
                rig = context.object
                src = rig.pose.bones.get(self.source_bone_name)
                if self.mode == 0:
                    src.urdf_props.ratio_target_bone = context.active_pose_bone.name
                else:
                    src.urdf_props.ratio_ref_bone = context.active_pose_bone.name
                rig.data.bones.active = src.bone
                context.window.cursor_set('DEFAULT')
                return {'FINISHED'}
        return {'RUNNING_MODAL'}

def write_urdf(context: bpy.types.Context, filepath: str, rig: bpy.types.Object, mesh_format: str) -> None:
    """
    Generates and writes the complete URDF file for the given armature.

    This function orchestrates the entire export process. It constructs the root
    <robot> XML element, adds required Gazebo plugins, finds the root(s) of the
    kinematic chain, and then recursively builds the URDF structure from there.

    Args:
        context: The current Blender context.
        filepath: The absolute path to write the URDF file to.
        rig: The armature object to export.
        mesh_format: The file format for the exported meshes (e.g., 'STL').
    """
    robot_name = rig.name
    robot = ET.Element('robot', name=robot_name)

    # --- Gazebo Plugin for ros2_control ---
    # This is a standard Gazebo plugin required to interface with ROS 2 controllers.
    gazebo = ET.SubElement(robot, 'gazebo')
    plugin = ET.SubElement(gazebo, 'plugin', name='gazebo_ros2_control', filename='libgazebo_ros2_control.so')
    ET.SubElement(plugin, 'robot_param').text = 'robot_description'
    ET.SubElement(plugin, 'robot_param_node').text = 'robot_state_publisher'

    # Find the root bone(s) of the armature. A robot can have multiple disconnected kinematic chains.
    root_bones = [b for b in rig.pose.bones if not b.parent]
    if not root_bones:
        print("URDF Export Error: No root bone found in the armature.")
        return

    # A set to keep track of links that have already been processed.
    # This is crucial for robots with multiple roots or complex branching.
    processed_links: Set[str] = set()

    for root_bone in root_bones:
        add_link_recursive(robot, root_bone, context, robot_name, mesh_format, processed_links)

    # --- Write the final XML file ---
    try:
        tree = ET.ElementTree(robot)
        ET.indent(tree, space="  ", level=0)
        tree.write(filepath, encoding='utf-8', xml_declaration=True)
    except IOError as e:
        print(f"Error writing URDF file to {filepath}: {e}")
        # It would be beneficial to report this error to the user via the UI.
        # self.report({'ERROR'}, f"File I/O Error: {e}") # (if in an operator)

def add_link_recursive(
    robot: ET.Element,
    bone: bpy.types.PoseBone,
    context: bpy.types.Context,
    robot_name: str,
    mesh_format: str,
    processed_links: Set[str]
) -> None:
    """
    Recursively adds a <link> and its corresponding <joint> to the URDF tree.

    This function is the core of the export logic. For each bone, it:
    1. Creates a <link> element with the bone's name.
    2. Adds <visual>, <collision>, and <inertial> tags for all associated meshes.
    3. Adds Gazebo-specific tags for simulation appearance.
    4. If the bone has a parent, it creates a <joint> element to connect it.
    5. Recursively calls itself for all child bones.

    Args:
        robot: The root <robot> XML element.
        bone: The current bone being processed.
        context: The current Blender context.
        robot_name: The name of the robot (used for package paths).
        mesh_format: The file format for exported meshes.
        processed_links: A set to track processed links to prevent duplicates in
                         complex or multi-root armatures.
    """
    if bone.name in processed_links:
        return
    processed_links.add(bone.name)

    link = ET.SubElement(robot, 'link', name=bone.name)
    child_meshes = get_all_children_objects(bone, context)

    # --- Add Visual and Collision Tags ---
    # A single link can be composed of multiple visual and collision meshes.
    if not child_meshes:
        # Add a dummy box to represent the link if no mesh is attached.
        # This can be useful for visualizing the kinematic chain.
        add_dummy_visual(link, bone)
    else:
        for mesh_obj in child_meshes:
            add_visual(link, bone, mesh_obj, robot_name, mesh_format)
            add_collision(link, bone, mesh_obj, robot_name, mesh_format)

    # --- Add Inertial Tag (once per link) ---
    # The inertial properties are defined for the link as a whole.
    add_inertial(link, bone)

    # --- Add Gazebo-specific Tags (e.g., material for simulation) ---
    add_gazebo_tags(link, bone)

    # --- Add Joint connecting this link to its parent ---
    if bone.parent:
        add_joint(robot, parent_bone=bone.parent, child_bone=bone)

    # --- Add Transmission Tag (for ros2_control) ---
    add_transmission(robot, bone)

    # --- Recurse for all children ---
    for child_bone in bone.children:
        add_link_recursive(robot, child_bone, context, robot_name, mesh_format, processed_links)

def add_dummy_visual(link_element: ET.Element, bone: bpy.types.PoseBone) -> None:
    """Adds a placeholder box visual for links with no associated mesh."""
    visual = ET.SubElement(link_element, 'visual')
    ET.SubElement(visual, 'origin', xyz="0 0 0", rpy="0 0 0")
    geometry = ET.SubElement(visual, 'geometry')
    box = ET.SubElement(geometry, 'box')
    size = max(0.01, bone.length) # Ensure a minimum size
    box.set('size', f"{size} {size} {size}")
    material = ET.SubElement(visual, 'material', name=f"{bone.name}_dummy_mat")
    ET.SubElement(material, 'color', rgba="0.7 0.7 0.7 1.0")


def add_visual(link_element: ET.Element, bone: bpy.types.PoseBone, mesh_obj: bpy.types.Object, robot_name: str, mesh_format: str) -> None:
    """
    Adds a <visual> tag to a link for a specific mesh object.

    Args:
        link_element: The <link> XML element to add to.
        bone: The bone that defines the link's frame of reference.
        mesh_obj: The mesh object to create the visual tag for.
        robot_name: The name of the robot package.
        mesh_format: The file format for the mesh.
    """
    visual = ET.SubElement(link_element, 'visual')

    # --- Origin Tag ---
    # The <origin> tag defines the pose of the visual mesh relative to the
    # link's origin (which is the bone's head).
    #
    # Transformation Logic:
    # 1. `bone.matrix`: The transform of the bone's head from Armature Space to World Space.
    #    This defines the link's coordinate frame.
    # 2. `mesh_obj.matrix_local`: The transform of the mesh object relative to its parent (the armature).
    # 3. `bone.matrix.inverted()`: Creates a matrix that transforms from World Space into the
    #    bone's (link's) local space.
    # 4. `bone.matrix.inverted() @ mesh_obj.matrix_local`: This multiplication results in the
    #    transform of the mesh object directly relative to the bone's head, which is
    #    exactly what the URDF <origin> tag requires.
    relative_matrix = bone.matrix.inverted() @ mesh_obj.matrix_local
    loc, rot, _ = relative_matrix.decompose()
    rpy = rot.to_euler('XYZ')

    origin = ET.SubElement(visual, 'origin')
    origin.set('xyz', f"{loc.x:.6f} {loc.y:.6f} {loc.z:.6f}")
    origin.set('rpy', f"{rpy.x:.6f} {rpy.y:.6f} {rpy.z:.6f}")

    # --- Geometry Tag ---
    geometry = ET.SubElement(visual, 'geometry')
    mesh_elem = ET.SubElement(geometry, 'mesh')
    mesh_ext = mesh_format.lower()
    if mesh_format == 'GLTF':
        mesh_ext = 'glb'

    mesh_filepath = os.path.join("meshes", f"{mesh_obj.name}.{mesh_ext}")
    mesh_elem.set('filename', f"package://{robot_name}/{mesh_filepath}")
    mesh_elem.set('scale', "1 1 1") # Scale is baked into the exported mesh.

    # --- Material Tag ---
    # Use the material from the bone's properties for consistency across the link.
    material_props = bone.urdf_props.material
    mat_name = f"{bone.name}_material" # Use bone name for a single link material
    material = ET.SubElement(visual, 'material', name=mat_name)
    color = material_props.color
    ET.SubElement(material, 'color', rgba=f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} {color[3]:.3f}")
    if material_props.texture and material_props.texture.name:
        ET.SubElement(material, 'texture', filename=f"package://{robot_name}/textures/{material_props.texture.name}")

def add_collision(link_element: ET.Element, bone: bpy.types.PoseBone, mesh_obj: bpy.types.Object, robot_name: str, mesh_format: str) -> None:
    """
    Adds a <collision> tag to a link.

    It can use either the visual mesh itself or a dedicated collision object
    defined in the bone's properties.

    Args:
        link_element: The <link> XML element.
        bone: The bone defining the link's frame.
        mesh_obj: The primary visual mesh object (used as a fallback).
        robot_name: The name of the robot package.
        mesh_format: The file format for the mesh.
    """
    collision = ET.SubElement(link_element, 'collision')
    collision_props = bone.urdf_props.collision

    # Default to the visual mesh if no specific collision object is assigned.
    collision_obj = collision_props.collision_object if collision_props.collision_object else mesh_obj
    if not collision_obj: return

    # --- Origin Tag (same logic as visual) ---
    relative_matrix = bone.matrix.inverted() @ collision_obj.matrix_local
    loc, rot, _ = relative_matrix.decompose()
    rpy = rot.to_euler('XYZ')
    origin = ET.SubElement(collision, 'origin')
    origin.set('xyz', f"{loc.x:.6f} {loc.y:.6f} {loc.z:.6f}")
    origin.set('rpy', f"{rpy.x:.6f} {rpy.y:.6f} {rpy.z:.6f}")

    # --- Geometry Tag ---
    geometry = ET.SubElement(collision, 'geometry')
    shape = collision_props.shape
    # Use dimensions of the evaluated collision object for primitives.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_coll_obj = collision_obj.evaluated_get(depsgraph)
    dims = eval_coll_obj.dimensions

    if shape == 'MESH':
        mesh_elem = ET.SubElement(geometry, 'mesh')
        mesh_ext = mesh_format.lower()
        if mesh_format == 'GLTF':
            mesh_ext = 'glb'

        mesh_filepath = os.path.join("meshes", f"{collision_obj.name}.{mesh_ext}")
        mesh_elem.set('filename', f"package://{robot_name}/{mesh_filepath}")
        mesh_elem.set('scale', "1 1 1")
    elif shape == 'BOX':
        box = ET.SubElement(geometry, 'box')
        box.set('size', f"{dims.x:.6f} {dims.y:.6f} {dims.z:.6f}")
    elif shape == 'CYLINDER':
        cylinder = ET.SubElement(geometry, 'cylinder')
        # URDF assumes Z is the cylinder's height axis.
        radius = (dims.x + dims.y) / 4.0
        cylinder.set('radius', f"{radius:.6f}")
        cylinder.set('length', f"{dims.z:.6f}")
    elif shape == 'SPHERE':
        sphere = ET.SubElement(geometry, 'sphere')
        radius = (dims.x + dims.y + dims.z) / 6.0
        sphere.set('radius', f"{radius:.6f}")

def add_inertial(link_element: ET.Element, bone: bpy.types.PoseBone) -> None:
    """
    Adds the <inertial> tag to a link using properties from the bone.

    Args:
        link_element: The <link> XML element.
        bone: The bone containing the inertial properties.
    """
    inertial = ET.SubElement(link_element, 'inertial')
    inertial_props = bone.urdf_props.inertial
    ET.SubElement(inertial, 'mass', value=f"{inertial_props.mass:.6f}")

    # The origin of the inertial frame is the center of mass, relative to the link frame.
    com = inertial_props.center_of_mass
    ET.SubElement(inertial, 'origin', xyz=f"{com.x:.6f} {com.y:.6f} {com.z:.6f}", rpy="0 0 0")

    ET.SubElement(inertial, 'inertia',
                   ixx=f"{inertial_props.ixx:.6f}", iyy=f"{inertial_props.iyy:.6f}", izz=f"{inertial_props.izz:.6f}",
                   ixy=f"{inertial_props.ixy:.6f}", ixz=f"{inertial_props.ixz:.6f}", iyz=f"{inertial_props.iyz:.6f}")

def add_gazebo_tags(link_element: ET.Element, bone: bpy.types.PoseBone) -> None:
    """
    Adds Gazebo-specific tags to a link, such as material for simulation.

    Args:
        link_element: The <link> XML element.
        bone: The bone containing the material properties.
    """
    material_props = bone.urdf_props.material
    color = material_props.color

    # This <gazebo> tag with a 'reference' is a Gazebo extension.
    # It allows setting simulation-specific properties for the link.
    gazebo_tag = ET.SubElement(link_element, 'gazebo', reference=bone.name)
    material_tag = ET.SubElement(gazebo_tag, 'material')
    # Define the material script for Gazebo's rendering engine.
    ET.SubElement(material_tag, 'script').append(ET.Element('name', text='Gazebo/Grey'))
    # Set color properties for the simulator.
    ET.SubElement(material_tag, 'ambient').text = f"{color[0]} {color[1]} {color[2]} {color[3]}"
    ET.SubElement(material_tag, 'diffuse').text = f"{color[0]} {color[1]} {color[2]} {color[3]}"
    ET.SubElement(material_tag, 'specular').text = "0.1 0.1 0.1 1.0"
    ET.SubElement(material_tag, 'pbr') # Add empty PBR element for modern Gazebo versions

def add_joint(robot: ET.Element, parent_bone: bpy.types.PoseBone, child_bone: bpy.types.PoseBone) -> None:
    """
    Adds a <joint> tag to the robot, connecting a child link to a parent link.

    Args:
        robot: The root <robot> XML element.
        parent_bone: The parent bone in the kinematic chain.
        child_bone: The child bone being connected.
    """
    props = child_bone.urdf_props
    joint_type = props.joint_type
    if joint_type == 'none': # 'none' means it's just a link in the chain, not a joint.
        return

    # AI Editor Note: Treat 'base' as 'fixed' for URDF export compatibility.
    # The 'base' type is a Blender-only concept for a freely movable root.
    # In URDF, if it has a parent, it must be rigidly attached.
    export_joint_type = 'fixed' if joint_type == 'base' else joint_type

    joint = ET.SubElement(robot, 'joint', name=f"{parent_bone.name}_to_{child_bone.name}", type=export_joint_type)
    ET.SubElement(joint, 'parent', link=parent_bone.name)
    ET.SubElement(joint, 'child', link=child_bone.name)

    # --- Origin Tag ---
    # The joint's origin is the pose of the child bone's head relative to the
    # parent bone's head. This uses the same transformation logic as the visual/collision origin.
    relative_matrix = parent_bone.matrix.inverted() @ child_bone.matrix
    loc, rot, _ = relative_matrix.decompose()
    rpy = rot.to_euler('XYZ')
    origin = ET.SubElement(joint, 'origin')
    origin.set('xyz', f"{loc.x:.6f} {loc.y:.6f} {loc.z:.6f}")
    origin.set('rpy', f"{rpy.x:.6f} {rpy.y:.6f} {rpy.z:.6f}")

    # --- Axis Tag (for non-fixed joints) ---
    if export_joint_type not in ['fixed']:
        axis_elem = ET.SubElement(joint, 'axis')
        axis_enum = props.axis_enum

        # Convert UI enum to a vector. The axis is defined in the joint's local frame.
        if 'X' in axis_enum: axis_vec = mathutils.Vector((1, 0, 0))
        elif 'Y' in axis_enum: axis_vec = mathutils.Vector((0, 1, 0))
        else: axis_vec = mathutils.Vector((0, 0, 1)) # Z
        if '-' in axis_enum: axis_vec *= -1.0

        axis_elem.set('xyz', f"{axis_vec.x} {axis_vec.y} {axis_vec.z}")

    # --- Limit Tag (for revolute and prismatic joints) ---
    if export_joint_type in ['revolute', 'prismatic']:
        limit = ET.SubElement(joint, 'limit', effort="1000.0", velocity="1.0")
        if export_joint_type == 'revolute':
            limit.set('lower', f"{math.radians(props.lower_limit):.6f}")
            limit.set('upper', f"{math.radians(props.upper_limit):.6f}")
        else: # prismatic
            limit.set('lower', f"{props.lower_limit:.6f}")
            limit.set('upper', f"{props.upper_limit:.6f}")

    # --- Mimic Tag ---
    for mimic in props.mimic_drivers:
        # Find the full joint name for the mimic target.
        mimic_target_bone = robot.find(f".//link[@name='{mimic.target_bone}']..../joint")
        if mimic_target_bone is not None:
             ET.SubElement(joint, 'mimic', joint=mimic_target_bone.get('name'), multiplier=f"{mimic.ratio:.6f}")

def add_transmission(robot: ET.Element, bone: bpy.types.PoseBone) -> None:
    """
    Adds a <transmission> tag for a joint, required for ros2_control.

    Args:
        robot: The root <robot> XML element.
        bone: The bone whose joint needs a transmission.
    """
    props = bone.urdf_props
    if props.joint_type not in ['revolute', 'prismatic', 'continuous'] or not bone.parent:
        return

    joint_name = f"{bone.parent.name}_to_{bone.name}"
    trans_name = f"{joint_name}_transmission"
    trans_props = props.transmission

    transmission = ET.SubElement(robot, 'transmission', name=trans_name)
    ET.SubElement(transmission, 'type').text = trans_props.type
    joint_elem = ET.SubElement(transmission, 'joint', name=joint_name)
    ET.SubElement(joint_elem, 'hardwareInterface').text = trans_props.hardware_interface
    actuator_elem = ET.SubElement(transmission, 'actuator', name=f"{joint_name}_motor")
    ET.SubElement(actuator_elem, 'hardwareInterface').text = trans_props.hardware_interface
    ET.SubElement(actuator_elem, 'mechanicalReduction').text = str(trans_props.mechanical_reduction)


class URDF_OT_GenerateROS2Workspace(bpy.types.Operator):
    """Generates a standard ROS 2 workspace structure with a description package"""
    bl_idname = "urdf.generate_ros2_workspace"
    bl_label = "Generate ROS 2 Workspace"
    bl_description = "Create a full ROS 2 workspace structure (src, build, install, log) and a description package template"
    bl_options = {'REGISTER', 'UNDO'}

    workspace_name: bpy.props.StringProperty(
        name="Workspace Name",
        default="ros2_ws",
        description="Name of the workspace directory to create"
    )
    directory: bpy.props.StringProperty(
        name="Workspace Path",
        description="Root directory for the ROS 2 workspace",
        subtype='DIR_PATH'
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.directory:
            self.report({'ERROR'}, "Invalid directory path")
            return {'CANCELLED'}

        workspace_root = os.path.join(self.directory, self.workspace_name)
        rig = context.scene.urdf_active_rig
        robot_name = rig.name if rig else "my_robot"
        # Sanitize robot name for ROS 2 (lowercase, underscores)
        pkg_name = re.sub(r'[^a-z0-9_]', '_', robot_name.lower()) + "_description"

        # --- Level 1: The Workspace ---
        for folder in ['src', 'build', 'install', 'log']:
            os.makedirs(os.path.join(workspace_root, folder), exist_ok=True)

        # --- Level 2: The Package ---
        pkg_root = os.path.join(workspace_root, 'src', pkg_name)
        
        # --- Level 3: Functional Directories ---
        # Create standard folders
        for folder in ['launch', 'config', 'urdf', 'meshes', 'worlds', 'maps', 'include', 'src', 'test']:
            os.makedirs(os.path.join(pkg_root, folder), exist_ok=True)
        
        # Create subfolders for meshes
        os.makedirs(os.path.join(pkg_root, 'meshes', 'visual'), exist_ok=True)
        os.makedirs(os.path.join(pkg_root, 'meshes', 'collision'), exist_ok=True)

        # 1. package.xml (The Manifest)
        package_xml_content = f"""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{pkg_name}</name>
  <version>0.0.0</version>
  <description>The {pkg_name} package</description>
  <maintainer email="user@todo.todo">user</maintainer>
  <license>TODO: License declaration</license>

  <buildtool_depend>ament_cmake</buildtool_depend>

  <depend>urdf</depend>
  <depend>xacro</depend>
  <depend>rclcpp</depend>
  <depend>rclpy</depend>
  <depend>std_msgs</depend>
  <depend>gazebo_ros</depend>

  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>
"""
        with open(os.path.join(pkg_root, 'package.xml'), 'w') as f:
            f.write(package_xml_content)

        # 2. CMakeLists.txt (Build Rules)
        cmake_content = f"""cmake_minimum_required(VERSION 3.8)
project({pkg_name})

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(urdf REQUIRED)
find_package(xacro REQUIRED)

install(
  DIRECTORY config launch meshes urdf worlds maps
  DESTINATION share/${{PROJECT_NAME}}
)

ament_package()
"""
        with open(os.path.join(pkg_root, 'CMakeLists.txt'), 'w') as f:
            f.write(cmake_content)

        # 3. Dummy Launch File
        launch_content = f"""import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([os.path.join(
                get_package_share_directory('gazebo_ros'), 'launch', 'gazebo.launch.py')]),
        ),
    ])
"""
        # AI Editor Note: Renamed to gazebo.launch.py to match the functional requirement.
        # This ensures the template is ready for Gazebo simulation out of the box.
        with open(os.path.join(pkg_root, 'launch', 'gazebo.launch.py'), 'w') as f:
            f.write(launch_content)

        self.report({'INFO'}, f"Generated ROS 2 workspace at {workspace_root}")
        return {'FINISHED'}

class URDF_ExportItem(bpy.types.PropertyGroup):
    """Item for the export list"""
    rig: bpy.props.PointerProperty(type=bpy.types.Object, poll=lambda self, obj: obj.type == 'ARMATURE', name="Rig")

class URDF_UL_ExportList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "rig", text="", emboss=False, icon='OUTLINER_OB_ARMATURE')
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class URDF_OT_ExportList_Add(bpy.types.Operator):
    """Add selected armatures to the export list"""
    bl_idname = "urdf.export_list_add"
    bl_label = "Add Selected"
    
    def execute(self, context):
        added = 0
        for obj in context.selected_objects:
            if obj.type == 'ARMATURE':
                # Check if already in list
                if not any(item.rig == obj for item in context.scene.urdf_export_list):
                    item = context.scene.urdf_export_list.add()
                    item.rig = obj
                    added += 1
        if added == 0 and context.scene.urdf_active_rig:
             if not any(item.rig == context.scene.urdf_active_rig for item in context.scene.urdf_export_list):
                item = context.scene.urdf_export_list.add()
                item.rig = context.scene.urdf_active_rig
                added += 1
        return {'FINISHED'}

class URDF_OT_ExportList_Remove(bpy.types.Operator):
    """Remove active item from export list"""
    bl_idname = "urdf.export_list_remove"
    bl_label = "Remove"
    
    def execute(self, context):
        idx = context.scene.urdf_export_list_index
        try:
            context.scene.urdf_export_list.remove(idx)
            context.scene.urdf_export_list_index = min(max(0, idx - 1), len(context.scene.urdf_export_list) - 1)
        except:
            pass
        return {'FINISHED'}

class OPS_OT_Export(bpy.types.Operator, ExportHelper):
    bl_idname = "urdf.export_general"
    bl_label = "Export Robot Package"
    
    filename_ext = ".urdf"
    
    filter_glob: bpy.props.StringProperty(
        default="*.urdf",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context: bpy.types.Context) -> Set[str]:
        scene = context.scene
        
        # AI Editor Note: Determine which rigs to export (List vs Active)
        rigs_to_export = []
        if len(scene.urdf_export_list) > 0:
            rigs_to_export = [item.rig for item in scene.urdf_export_list if item.rig]
        elif scene.urdf_active_rig:
            rigs_to_export = [scene.urdf_active_rig]
            
        if not rigs_to_export:
            self.report({'ERROR'}, "No rigs selected for export.")
            return {'CANCELLED'}

        # --- Base path and name from the file dialog ---
        base_dir = os.path.dirname(self.filepath)
        robot_name_from_file = os.path.splitext(os.path.basename(self.filepath))[0]

        # Sanitize package name for ROS 2 (lowercase, underscores)
        # Used if generating config files
        pkg_name = re.sub(r'[^a-z0-9_]', '_', robot_name_from_file.lower())

        # --- URDF Export Logic ---
        if scene.urdf_export_as_urdf:
            mesh_format = scene.urdf_export_mesh_format
            
            # Export URDF for each rig
            for i, rig in enumerate(rigs_to_export):
                # If exporting multiple, use rig name. If single, use filename.
                if len(rigs_to_export) > 1:
                    urdf_name = f"{rig.name}.urdf"
                else:
                    urdf_name = f"{robot_name_from_file}.urdf"
                
                urdf_filepath = os.path.join(base_dir, urdf_name)
                write_urdf(context, urdf_filepath, rig, mesh_format)

            # --- Generate Package Config (package.xml, CMakeLists.txt) ---
            if scene.urdf_export_check_config:
                package_xml_content = f"""<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>{pkg_name}</name>
  <version>0.0.0</version>
  <description>The {pkg_name} package</description>
  <maintainer email="user@todo.todo">user</maintainer>
  <license>TODO: License declaration</license>

  <buildtool_depend>ament_cmake</buildtool_depend>

  <depend>urdf</depend>
  <depend>xacro</depend>
  <depend>rclcpp</depend>
  <depend>rclpy</depend>
  <depend>std_msgs</depend>
  <depend>gazebo_ros</depend>

  <test_depend>ament_lint_auto</test_depend>
  <test_depend>ament_lint_common</test_depend>

  <export>
    <build_type>ament_cmake</build_type>
  </export>
</package>"""
                with open(os.path.join(base_dir, 'package.xml'), 'w') as f:
                    f.write(package_xml_content)

                cmake_content = f"""cmake_minimum_required(VERSION 3.8)
project({pkg_name})

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(urdf REQUIRED)
find_package(xacro REQUIRED)

install(
  DIRECTORY config launch meshes urdf worlds maps
  DESTINATION share/${{PROJECT_NAME}}
)

ament_package()"""
                with open(os.path.join(base_dir, 'CMakeLists.txt'), 'w') as f:
                    f.write(cmake_content)

            # --- Generate Launch Files ---
            if scene.urdf_export_check_launch:
                launch_dir = os.path.join(base_dir, 'launch')
                os.makedirs(launch_dir, exist_ok=True)
                
                # Generate launch file for each rig
                for rig in rigs_to_export:
                    if len(rigs_to_export) > 1:
                        launch_filename = f"gazebo_{rig.name}.launch.py"
                        urdf_name = f"{rig.name}.urdf"
                    else:
                        launch_filename = "gazebo.launch.py"
                        urdf_name = f"{robot_name_from_file}.urdf"
                        
                    launch_content = f"""import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    urdf_file = '{os.path.join(base_dir, urdf_name)}'
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([os.path.join(
                get_package_share_directory('gazebo_ros'), 'launch', 'gazebo.launch.py')]),
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{{'robot_description': robot_desc, 'use_sim_time': True}}]
        ),
        Node(
            package='gazebo_ros',
            executable='spawn_entity.py',
            arguments=['-topic', 'robot_description', '-entity', '{rig.name}'],
            output='screen'
        )
    ])"""
                    # Note: The launch file above uses a hardcoded path for simplicity in this context, 
                    # but in a real installed package it would use get_package_share_directory.
                    # For a generated export, we provide a basic template.
                    with open(os.path.join(launch_dir, launch_filename), 'w') as f:
                        f.write(launch_content)

            meshes_to_export: Set[bpy.types.Object] = set()
            for rig in rigs_to_export:
                for bone in rig.pose.bones:
                    visual_meshes = get_all_children_objects(bone, context)
                    meshes_to_export.update(visual_meshes)
                    collision_props = bone.urdf_props.collision
                    if collision_props.shape == 'MESH':
                        collision_obj = collision_props.collision_object
                        if collision_obj and collision_obj.type == 'MESH':
                            meshes_to_export.add(collision_obj)

            if meshes_to_export and scene.urdf_export_check_meshes:
                meshes_dir = os.path.join(base_dir, "meshes")
                textures_dir = os.path.join(base_dir, "textures")
                os.makedirs(meshes_dir, exist_ok=True)
                os.makedirs(textures_dir, exist_ok=True)

                original_selection = context.selected_objects
                original_active = context.view_layer.objects.active
                for o in context.view_layer.objects:
                    o.select_set(False)
                
                wm = context.window_manager
                wm.progress_begin(0, len(meshes_to_export))
                
                for i, obj in enumerate(meshes_to_export):
                    wm.progress_update(i)
                    context.view_layer.objects.active = obj
                    obj.select_set(True)
                    
                    try:
                        if mesh_format == 'STL':
                            mesh_filepath = os.path.join(meshes_dir, f"{obj.name}.stl")
                            bpy.ops.export_mesh.stl(filepath=mesh_filepath, use_selection=True, global_scale=1.0, use_mesh_modifiers=True)
                        elif mesh_format == 'DAE':
                            mesh_filepath = os.path.join(meshes_dir, f"{obj.name}.dae")
                            bpy.ops.wm.collada_export(filepath=mesh_filepath, selected=True, apply_modifiers=True)
                        elif mesh_format == 'GLTF':
                            mesh_filepath = os.path.join(meshes_dir, f"{obj.name}.glb")
                            bpy.ops.export_scene.gltf(filepath=mesh_filepath, use_selection=True, export_format='GLB', export_apply=True, export_yup=True)

                    except Exception as e:
                        self.report({'WARNING'}, f"Could not export mesh '{obj.name}' for URDF: {e}")
                    
                    obj.select_set(False)

                    if mesh_format in ['DAE', 'GLTF'] and scene.urdf_export_check_textures:
                        if obj.active_material and obj.active_material.use_nodes:
                            for node in obj.active_material.node_tree.nodes:
                                if node.type == 'TEX_IMAGE' and node.image:
                                    try:
                                        texture_filepath = os.path.join(textures_dir, node.image.name)
                                        if not os.path.exists(texture_filepath) and node.image.has_data:
                                            node.image.save(filepath=texture_filepath)
                                    except Exception as e:
                                        self.report({'WARNING'}, f"Could not save texture '{node.image.name}': {e}")
                
                wm.progress_end()

                for o in context.view_layer.objects:
                    o.select_set(False)
                for obj in original_selection:
                    obj.select_set(True)
                context.view_layer.objects.active = original_active
            
            self.report({'INFO'}, f"Exported URDF package to {base_dir}")

        # --- glTF Export Logic ---
        if scene.urdf_export_as_gltf:
            gltf_filepath = os.path.join(base_dir, f"{robot_name_from_file}.glb")
            try:
                # Select rig and all its children for export
                # AI Editor Note: Select all rigs if multiple are present
                bpy.ops.object.select_all(action='DESELECT')
                for rig in rigs_to_export:
                    rig.select_set(True)
                    for child in rig.children_recursive:
                        child.select_set(True)
                bpy.ops.export_scene.gltf(
                    filepath=gltf_filepath,
                    use_selection=True,
                    export_format='GLB',
                    export_apply=True,
                    export_textures=scene.urdf_export_gltf_textures,
                    export_normals=scene.urdf_export_gltf_normals,
                    export_animations=scene.urdf_export_gltf_animations,
                    export_yup=True
                )
                self.report({'INFO'}, f"Exported scene as glTF to {gltf_filepath}")
            except Exception as e:
                self.report({'ERROR'}, f"Failed to export glTF: {e}")

        if not scene.urdf_export_as_urdf and not scene.urdf_export_as_gltf:
            self.report({'WARNING'}, "No export format selected.")
            return {'CANCELLED'}

        return {'FINISHED'}

class URDF_OT_ExportSelected(bpy.types.Operator, ExportHelper):
    """Export selected objects to a specific format with geometry and texture data"""
    bl_idname = "urdf.export_selected"
    bl_label = "Export Selected Mesh"
    bl_description = "Export selected objects to USD, glTF, OBJ, etc. for external software (Rhino, etc.)"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext: bpy.props.StringProperty(default="", options={'HIDDEN'})
    
    filter_glob: bpy.props.StringProperty(
        default="*.usdc;*.usda;*.glb;*.gltf;*.obj;*.fbx;*.stl",
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        fmt = context.scene.urdf_quick_export_format
        if fmt == 'USD': self.filename_ext = ".usdc"
        elif fmt == 'GLTF': self.filename_ext = ".glb"
        elif fmt == 'OBJ': self.filename_ext = ".obj"
        elif fmt == 'FBX': self.filename_ext = ".fbx"
        elif fmt == 'STL': self.filename_ext = ".stl"
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        fmt = context.scene.urdf_quick_export_format
        fpath = self.filepath
        
        if not fpath.lower().endswith(self.filename_ext):
            fpath += self.filename_ext

        try:
            if fmt == 'USD':
                bpy.ops.wm.usd_export(filepath=fpath, selected_objects_only=True, export_materials=True, export_textures=True, export_uvmaps=True, export_normals=True)
            elif fmt == 'GLTF':
                bpy.ops.export_scene.gltf(filepath=fpath, use_selection=True, export_format='GLB', export_apply=True, export_texcoords=True, export_normals=True)
            elif fmt == 'OBJ':
                bpy.ops.wm.obj_export(filepath=fpath, export_selected_objects=True, export_materials=True, export_uv=True, export_normals=True, apply_modifiers=True)
            elif fmt == 'FBX':
                bpy.ops.export_scene.fbx(filepath=fpath, use_selection=True, use_mesh_modifiers=True, mesh_smooth_type='FACE', path_mode='COPY', embed_textures=True)
            elif fmt == 'STL':
                bpy.ops.export_mesh.stl(filepath=fpath, use_selection=True, use_mesh_modifiers=True)
            
            self.report({'INFO'}, f"Exported selected to {fpath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

class OPS_OT_TogglePlacement(bpy.types.Operator):
    bl_idname = "urdf.toggle_placement"
    bl_label = "Toggle Joint Placement Mode"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        rig = context.scene.urdf_active_rig
        if not rig:
            self.report({'WARNING'}, "No active rig selected.")
            return {'CANCELLED'}

        is_entering_placement = not context.scene.urdf_placement_mode

        if is_entering_placement:
            context.scene.urdf_placement_mode = True
            
            if rig.animation_data:
                for d in rig.animation_data.drivers:
                    d.mute = True
            
            # --- AI Editor Note: Robust Context Management ---
            # To safely switch to Pose Mode, we must first ensure that the target
            # armature ('rig') is the active object in the view layer.
            # The following lines guarantee the correct context before calling the mode_set operator.
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT') # Go to object mode first to be safe
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = rig
            rig.select_set(True)

            # Now that the rig is active, we can safely switch to Pose Mode.
            bpy.ops.object.mode_set(mode='POSE')

            # This call will unlock the bones because urdf_placement_mode is now True
            for pb in rig.pose.bones:
                apply_native_constraints(pb) 
            
            self.report({'INFO'}, "Joint placement mode enabled.")

        else: # Exiting placement mode
            context.scene.urdf_placement_mode = False

            # --- AI Editor Note: Robust Context Management ---
            # Ensure the rig is active before performing mode changes or pose operations.
            if context.view_layer.objects.active != rig or rig.mode != 'POSE':
                # Go to object mode first to be safe, e.g. if in edit mode on another object
                if context.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
                bpy.ops.object.select_all(action='DESELECT')
                context.view_layer.objects.active = rig
                rig.select_set(True)
                bpy.ops.object.mode_set(mode='POSE')

            # Apply the current pose as the new rest pose for the armature.
            bpy.ops.pose.armature_apply(selected=False)
            
            # --- AI Editor Note: Update drivers AFTER applying pose to prevent snapping ---
            # When the rest pose is applied, the offsets in existing drivers become invalid.
            # We must iterate through all mimic relationships and re-apply the driver logic
            # to recalculate the offsets based on the new rest pose.
            for pb in rig.pose.bones:
                if hasattr(pb, 'urdf_props') and pb.urdf_props.mimic_drivers:
                    for mimic in pb.urdf_props.mimic_drivers:
                        # Re-run the driver setup to update the expression with the new offset.
                        # The 'invert' setting is read from the bone's single 'ratio_invert' property,
                        # consistent with how new mimic drivers are created.
                        core.add_native_driver_relation(pb, mimic.target_bone, mimic.ratio, pb.urdf_props.ratio_invert)

            if rig.animation_data:
                for d in rig.animation_data.drivers:
                    d.mute = False

            # --- RESTORE CONSTRAINTS ---
            # Now that placement mode is off, re-apply the constraints.
            for pb in rig.pose.bones:
                apply_native_constraints(pb)

            self.report({'INFO'}, "Joint placement mode disabled.")

        context.view_layer.update()
        return {'FINISHED'}

class OPS_OT_CreateRig(bpy.types.Operator):
    bl_idname = "urdf.create_rig"
    bl_label = "Create New Robot"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        base_name = "New_Kinematics"
        name = base_name
        count = 2
        while name in context.scene.objects:
            name = f"{count}_Kinematics"
            count += 1
        armature_data = bpy.data.armatures.new(name + "_Data")
        rig = bpy.data.objects.new(name, armature_data)
        rig.location = context.scene.cursor.location # AI Editor Note: Create rig at cursor location
        context.view_layer.active_layer_collection.collection.objects.link(rig)
        rig.show_in_front = True
        rig.display_type = 'WIRE'
        armature_data.display_type = 'STICK'
        context.scene.urdf_active_rig = rig
        for o in context.selected_objects: o.select_set(False)
        rig.select_set(True)
        context.view_layer.objects.active = rig
        return {'FINISHED'}

class URDF_OT_MergeArmatures(bpy.types.Operator):
    """Merge selected armatures into a new armature workspace"""
    bl_idname = "urdf.merge_armatures"
    bl_label = "Merge Armatures"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and 
                context.active_object and 
                context.active_object.type == 'ARMATURE' and 
                len([o for o in context.selected_objects if o.type == 'ARMATURE']) > 1)

    def execute(self, context: bpy.types.Context) -> Set[str]:
        old_target_rig = context.active_object
        # --- AI Editor Note: ReferenceError Fix ---
        # Store the name of the original rig before it gets deleted. The old_target_rig
        # object reference becomes invalid after the original objects are removed.
        old_target_rig_name = old_target_rig.name
        old_armatures = [o for o in context.selected_objects if o.type == 'ARMATURE']
        
        # 1. Collect all objects to copy (Armatures + Recursive Children)
        # We use an iterative approach to find all descendants to ensure we get the full hierarchy.
        objects_to_copy = set(old_armatures)
        all_scene_objects = set(context.scene.objects)
        
        while True:
            children = {o for o in all_scene_objects if o.parent in objects_to_copy and o not in objects_to_copy}
            if not children:
                break
            objects_to_copy.update(children)
            
        # 2. Duplicate into New Workspace
        bpy.ops.object.select_all(action='DESELECT')
        objects_to_delete = [] # Keep track of objects we successfully select for duplication

        for obj in objects_to_copy:
            # --- AI Editor Note: Fix for disappearing objects ---
            # Blender's duplicate operator ignores hidden objects. We must ensure
            # all parts of the hierarchy are visible and selectable before duplication.
            # Since the originals will be deleted, we don't need to restore their state.
            obj.hide_viewport = False
            obj.hide_set(False)
            obj.hide_select = False
            try:
                obj.select_set(True)
                objects_to_delete.append(obj)
            except RuntimeError:
                # Object is likely not in the current View Layer (e.g. disabled collection).
                # We cannot duplicate it, so we must NOT delete it later to prevent data loss.
                continue
            
        # Ensure the main rig is active so its copy becomes the new main rig
        context.view_layer.objects.active = old_target_rig
        
        bpy.ops.object.duplicate(linked=False)
        
        # The selection now contains the new copies.
        new_target_rig = context.active_object
        new_objects = context.selected_objects
        
        # Identify the new armatures to be joined (excluding the target)
        new_armatures_to_join = [o for o in new_objects if o.type == 'ARMATURE' and o != new_target_rig]
        # --- AI Editor Note: Identify armatures for joining and remapping ---
        # This set is created before the join operation, so it holds valid references
        # to the armature copies that will be consumed.
        new_armatures_to_join_set = set(new_armatures_to_join)
        
        # --- AI Editor Note: Pre-Join Bone Renaming ---
        # We must ensure unique bone names BEFORE joining to preserve Vertex Groups and parent relationships.
        # Blender's join operator renames colliding bones (e.g. "Bone" -> "Bone.001") but does NOT
        # update the Vertex Groups or parent_bone references on child meshes, causing them to detach or deform incorrectly.
        
        existing_bone_names = {b.name for b in new_target_rig.data.bones}
        
        for rig in new_armatures_to_join:
            # Snapshot of current rig's bone names to avoid collision within itself during renaming
            current_rig_bone_names = {b.name for b in rig.data.bones}
            
            # Find dependent objects for this rig
            dependent_objects = []
            for obj in new_objects:
                if obj.type == 'MESH':
                    if obj.parent == rig:
                        dependent_objects.append(obj)
                    elif any(m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers):
                        dependent_objects.append(obj)
            
            for bone in rig.data.bones:
                if bone.name in existing_bone_names:
                    old_name = bone.name
                    new_name = old_name
                    counter = 1
                    while new_name in existing_bone_names or new_name in current_rig_bone_names:
                        new_name = f"{old_name}.{counter:03d}"
                        counter += 1
                    
                    bone.name = new_name
                    existing_bone_names.add(new_name)
                    
                    # Update references in dependent objects
                    for obj in dependent_objects:
                        # Update Vertex Groups
                        vg = obj.vertex_groups.get(old_name)
                        if vg: vg.name = new_name
                        
                        # Update Parent Bone
                        if obj.parent == rig and obj.parent_type == 'BONE' and obj.parent_bone == old_name:
                            obj.parent_bone = new_name
                            
                    # Update Constraints on any new object targeting this rig/bone
                    for obj in new_objects:
                        for con in obj.constraints:
                            if hasattr(con, 'target') and con.target == rig and hasattr(con, 'subtarget') and con.subtarget == old_name:
                                con.subtarget = new_name
                                
                    # Update Drivers
                    for obj in new_objects:
                        if obj.animation_data and obj.animation_data.drivers:
                            for d in obj.animation_data.drivers:
                                for v in d.driver.variables:
                                    for t in v.targets:
                                        if t.id == rig:
                                            if hasattr(t, 'bone_target') and t.bone_target == old_name:
                                                t.bone_target = new_name
                                            if hasattr(t, 'data_path') and f'["{old_name}"]' in t.data_path:
                                                t.data_path = t.data_path.replace(f'["{old_name}"]', f'["{new_name}"]')
                else:
                    existing_bone_names.add(bone.name)
        
        # 3. Join Armatures
        # Select only the armatures for joining
        bpy.ops.object.select_all(action='DESELECT')
        new_target_rig.select_set(True)
        context.view_layer.objects.active = new_target_rig
        
        for rig_to_join in new_armatures_to_join:
            rig_to_join.select_set(True)
            
        bpy.ops.object.join()
        
        # --- AI Editor Note: Post-Join Pointer Remapping ---
        # After joining, any Drivers or Geometry Nodes on the duplicated objects
        # that pointed to the now-deleted armatures are broken. This loop
        # iterates through all newly created objects and redirects those pointers
        # to the final merged armature, ensuring all procedural setups continue to function.
        for obj in new_objects:
            try:
                # This check is the most robust way to see if the object reference
                # from our list is still valid after the join operation.
                if obj.name not in bpy.data.objects:
                    continue
            except ReferenceError:
                # This handles the case where the object reference itself is invalid.
                continue
                
            # A. Remap Drivers
            if obj.animation_data and obj.animation_data.drivers:
                for d in obj.animation_data.drivers:
                    for v in d.driver.variables:
                        for t in v.targets:
                            try:
                                # Check if the driver target was one of the armatures we just joined.
                                if t.id in new_armatures_to_join_set:
                                    t.id = new_target_rig
                            except ReferenceError:
                                # The target ID might be an invalid reference itself. Safe to ignore.
                                pass

            # B. Remap Geometry Node Inputs
            for mod in obj.modifiers:
                if mod.type == 'NODES' and mod.node_group:
                    # Iterate through the modifier's interface sockets.
                    for item in mod.node_group.interface.items_tree:
                        if item.item_type == 'SOCKET' and item.socket_type == 'NodeSocketObject':
                            try:
                                # Get the object currently assigned to this input.
                                input_obj = mod[item.identifier]
                                # If it was one of the joined armatures, re-point it.
                                if input_obj in new_armatures_to_join_set:
                                    mod[item.identifier] = new_target_rig
                            except (KeyError, ReferenceError):
                                # This can happen if the input isn't set or the object is gone.
                                # It's safe to ignore these cases.
                                pass

            # C. Remap Constraints
            # Constraints on the new objects might point to the armature copies that are about to be joined/deleted.
            # We redirect them to the new merged rig to prevent broken links.
            for con in obj.constraints:
                if hasattr(con, 'target') and con.target in new_armatures_to_join_set:
                    con.target = new_target_rig

            # D. Remap Modifiers
            # Armature modifiers (and others like Hook, SimpleDeform) might point to the consumed armatures.
            # If these links break, the mesh might jump or disappear.
            for mod in obj.modifiers:
                if hasattr(mod, 'object') and mod.object in new_armatures_to_join_set:
                    mod.object = new_target_rig
                if mod.type == 'ARRAY' and mod.use_object_offset and mod.offset_object in new_armatures_to_join_set:
                    mod.offset_object = new_target_rig
        
        # 5. Delete Old Data
        # Remove the original objects to complete the "move to workspace" effect
        for obj in objects_to_delete:
            if obj.name in context.scene.objects:
                 bpy.data.objects.remove(obj, do_unlink=True)

        # 6. Finalize
        new_target_rig.name = f"{old_target_rig_name}_Merged"
        context.scene.urdf_active_rig = new_target_rig
        
        # AI Editor Note: Force a full update of gizmos and constraints on the new rig.
        # This ensures that the merged result is clean and fully functional.
        update_all_gizmos(context.scene, context)
        
        self.report({'INFO'}, f"Merged into new workspace '{new_target_rig.name}'")
        return {'FINISHED'}

class URDF_OT_PurgeBones(bpy.types.Operator):
    """Removes selected bones and unparents their associated meshes, cleaning up the rig."""
    bl_idname = "urdf.purge_bones"
    bl_label = "Purge Selected Bones"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode == 'OBJECT':
            return len(context.selected_objects) > 0
        elif context.mode == 'POSE':
            return len(context.selected_pose_bones) > 0
        return False

    def execute(self, context: bpy.types.Context) -> Set[str]:
        rig = context.scene.urdf_active_rig
        bones_to_remove = set()
        objects_to_unparent = []

        # 1. Identify targets based on mode
        if context.mode == 'OBJECT':
            if not rig:
                self.report({'WARNING'}, "No active rig set.")
                return {'CANCELLED'}
            
            for obj in context.selected_objects:
                if obj.parent == rig and obj.parent_type == 'BONE' and obj.parent_bone:
                    bones_to_remove.add(obj.parent_bone)
                    objects_to_unparent.append(obj)
        
        elif context.mode == 'POSE':
            rig = context.object
            for pb in context.selected_pose_bones:
                bones_to_remove.add(pb.name)
                # Find children to unparent so they don't jump
                children = get_all_children_objects(pb, context)
                objects_to_unparent.extend(children)

        if not bones_to_remove:
            self.report({'WARNING'}, "No bones linked to selection found.")
            return {'CANCELLED'}

        # 2. Unparent objects to preserve transforms
        for obj in objects_to_unparent:
            mat = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = mat

        # 3. Delete bones in Edit Mode
        previous_mode = context.mode
        
        # AI Editor Note: Ensure we are in Object Mode before calling object selection operators.
        # This prevents RuntimeError when running from Pose Mode.
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Deselect everything first to avoid clutter
        bpy.ops.object.select_all(action='DESELECT')
        
        context.view_layer.objects.active = rig
        rig.select_set(True)
        
        bpy.ops.object.mode_set(mode='EDIT')
        
        armature = rig.data
        count = 0
        for bone_name in bones_to_remove:
            eb = armature.edit_bones.get(bone_name)
            if eb:
                armature.edit_bones.remove(eb)
                count += 1
        
        # 4. Restore context
        if previous_mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            # Reselect the objects that were unparented
            for obj in objects_to_unparent:
                obj.select_set(True)
            if objects_to_unparent:
                context.view_layer.objects.active = objects_to_unparent[0]
        else:
            bpy.ops.object.mode_set(mode='POSE')

        # --- 5. Cleanup unused gizmos ---
        # AI Editor Note: Garbage collect unused widget objects to keep the scene clean.
        # This ensures that when bones are purged, their visual widgets don't linger if unused.
        used_widgets = set()
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                for pb in obj.pose.bones:
                    if pb.custom_shape:
                        used_widgets.add(pb.custom_shape)
        
        widgets_coll = bpy.data.collections.get(WIDGETS_COLLECTION_NAME)
        if widgets_coll:
            widgets_to_remove = [w for w in widgets_coll.objects if w not in used_widgets]
            for widget in widgets_to_remove:
                bpy.data.objects.remove(widget, do_unlink=True)

        self.report({'INFO'}, f"Purged {count} bones and unparented {len(objects_to_unparent)} objects.")
        return {'FINISHED'}

class OPS_OT_ParentToActive(bpy.types.Operator):
    bl_idname = "urdf.parent_to_active"
    bl_label = "Parent Selected to Active"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context: bpy.types.Context) -> Set[str]:
        active_obj = context.active_object
        if not active_obj:
            return {'CANCELLED'}

        rig = None
        parent_bone_name = None

        # Case 1: The active object is the armature itself. The active pose bone is the target parent.
        if active_obj.type == 'ARMATURE':
            rig = active_obj
            parent_bone_name = context.active_pose_bone.name if context.active_pose_bone else None
        # Case 2: The active object is a mesh, likely a custom bone shape.
        # We need to find which bone in which armature is using this mesh.
        elif active_obj.type == 'MESH':
            # Iterate through all armatures in the scene
            for r in [o for o in context.scene.objects if o.type == 'ARMATURE']:
                for bone in r.pose.bones:
                    if bone.custom_shape == active_obj:
                        rig = r
                        parent_bone_name = bone.name
                        break # Found bone, stop searching in this armature
                if rig:
                    break # Found armature, stop searching other armatures
        if not rig or not parent_bone_name:
            return {'CANCELLED'}
        # AI Editor Note: Support both bone-to-bone and mesh-to-bone parenting.
        # Find all selected/sub-selected bones and meshes to parent.
        selected_bones = []
        selected_meshes = set()
        
        def gather_recursive(o):
            if o.type == 'MESH' and o != rig:
                selected_meshes.add(o)
            for child in o.children:
                gather_recursive(child)

        for obj in context.selected_objects:
            if obj.type == 'ARMATURE' and obj == rig:
                # If armature is selected, use pose bone selection
                for pbone in rig.pose.bones:
                    if pbone.bone.select and pbone.name != parent_bone_name:
                        selected_bones.append(pbone.name)
            else:
                gather_recursive(obj)
        
        if not selected_bones and not selected_meshes:
            return {'CANCELLED'}
        
        # 1. Mesh Parenting
        if selected_meshes:
            for mesh in selected_meshes:
                mesh.parent = rig
                mesh.parent_type = 'BONE'
                mesh.parent_bone = parent_bone_name
                
        # 2. Bone Parenting (requires Edit Mode)
        if selected_bones:
            context.view_layer.objects.active = rig
            bpy.ops.object.mode_set(mode='EDIT')
            eb_parent = rig.data.edit_bones.get(parent_bone_name)
            for name in selected_bones:
                eb_child = rig.data.edit_bones.get(name)
                if eb_child:
                    eb_child.use_connect = False
                    eb_child.parent = eb_parent
            bpy.ops.object.mode_set(mode='POSE')
            
        self.report({'INFO'}, f"Parented {len(selected_meshes)} meshes and {len(selected_bones)} bones to {parent_bone_name}")
        return {'FINISHED'}

class OPS_OT_EnterPoseMode(bpy.types.Operator):
    bl_idname = "urdf.enter_pose_mode"
    bl_label = "Pose Mode to Set Gizmos"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        # --- AI Editor Note: Context-Sensitive Rig Update ---
        # If the user has selected an armature (or a part of one), update the
        # active rig setting to match. This ensures the tool works on the
        # object the user is currently interacting with.
        target_rig = None
        active_obj = context.active_object

        if active_obj:
            if active_obj.type == 'ARMATURE':
                target_rig = active_obj
            elif active_obj.parent and active_obj.parent.type == 'ARMATURE':
                target_rig = active_obj.parent
        
        if not target_rig:
             for obj in context.selected_objects:
                if obj.type == 'ARMATURE':
                    target_rig = obj
                    break
        
        if target_rig:
            context.scene.urdf_active_rig = target_rig

        # --- AI Editor Note: AttributeError Fix ---
        # Ensure a rig exists before proceeding. This prevents 'rig' from being None if no
        # armature has been created or set as active yet.
        rig = ensure_default_rig(context)
        if not rig:
            self.report({'ERROR'}, "Could not find or create an active rig.")
            return {'CANCELLED'}
        
        # AI Editor Note: Smart bone selection.
        # If the active object is a mesh parented to a bone, select that bone upon entering Pose Mode.
        target_bone_name = None
        if active_obj and active_obj.parent == rig and active_obj.parent_type == 'BONE':
            target_bone_name = active_obj.parent_bone

        # AI Editor Note: Use manual deselection to avoid operator context errors.
        for o in context.view_layer.objects:
            o.select_set(False)
        context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='POSE')
        
        if target_bone_name:
            pbone = rig.pose.bones.get(target_bone_name)
            if pbone:
                rig.data.bones.active = pbone.bone
                pbone.bone.select = True
                
        return {'FINISHED'}
class OPS_OT_EnterObjectMode(bpy.types.Operator):
    bl_idname = "urdf.enter_object_mode"
    bl_label = "Object Mode"
    def execute(self, context: bpy.types.Context) -> Set[str]:
        bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}
def _calculate_bone_geometry(objs: List[bpy.types.Object], axis_orient: str, reference_obj: bpy.types.Object = None) -> Tuple[mathutils.Vector, mathutils.Vector, mathutils.Vector, float]:
    """
    Calculates the head, tail, and roll for a bone based on one or more mesh objects.
    
    AI Editor Note: Support for multiple objects ensures that complex links made of 
    several meshes (sub-selections) are correctly encompassed by a single bone.
    """
    if not isinstance(objs, (list, tuple, set)):
        objs = [objs]
    
    if not reference_obj:
        reference_obj = objs[0]
    
    mat = reference_obj.matrix_world
    inv_mat = mat.inverted()
    
    # 1. Build a combined bounding box in the reference object's local space
    all_points_local = []
    for o in objs:
        o_mat = o.matrix_world
        # Include all bbox corners if available (Meshes)
        if hasattr(o, 'bound_box') and o.bound_box:
            for b in o.bound_box:
                v_world = o_mat @ mathutils.Vector(b)
                all_points_local.append(inv_mat @ v_world)
        else:
            # Fallback to origin for objects without geometry (Empties)
            all_points_local.append(inv_mat @ o_mat.translation)
        
    if not all_points_local:
        return mat.translation, mat.translation + mathutils.Vector((0, 0.1, 0)), mathutils.Vector((0, 0, 1)), 0.1

    # 2. Extract head and orientation logic
    head_world = mat.translation
    tail_world: mathutils.Vector
    roll_vec_world: mathutils.Vector

    if axis_orient == 'AUTO':
        # --- Logic for Local Z-Axis Alignment ---
        y_vec_local = mathutils.Vector((0, 0, 1.0))
        z_vec_local = mathutils.Vector((1.0, 0, 0)) # Roll around local X

        # Calculate initial tail and roll in world space
        max_dist = max((p.dot(y_vec_local) for p in all_points_local), default=0.1)
        if max_dist < 0.001: max_dist = 0.1
        
        tail_local = y_vec_local * max_dist
        initial_tail_world = mat @ tail_local
        initial_roll_vec_world = mat.to_3x3() @ z_vec_local

        # Get the bone's initial orientation vectors in world space.
        y_vec_world = (initial_tail_world - head_world).normalized()
        z_vec_world = initial_roll_vec_world.normalized()
        x_vec_world = y_vec_world.cross(z_vec_world).normalized()

        # Initial orientation matrix (local to world)
        orient_mat = mathutils.Matrix((x_vec_world, y_vec_world, z_vec_world)).transposed()
        final_orient_mat = orient_mat

        # Decompose the final matrix to get the new world-space direction and roll vectors.
        new_y_vec_world = final_orient_mat.col[1]
        new_z_vec_world = final_orient_mat.col[2]

        # Recalculate the tail position and roll vector based on the new orientation.
        bone_length = (initial_tail_world - head_world).length
        tail_world = head_world + bone_length * new_y_vec_world
        roll_vec_world = new_z_vec_world
    else:
        # --- Logic for Local X, Y, Z Alignment ---
        is_neg = axis_orient.startswith("-")
        axis_char = axis_orient.replace("-", "")
        
        # Define bone's primary axis (Y) and roll axis (Z) in the REFERENCE's LOCAL space.
        if axis_char == 'X':
            y_vec_local = mathutils.Vector((1, 0, 0))
            roll_vec_local = mathutils.Vector((0, 0, 1))
        elif axis_char == 'Y':
            y_vec_local = mathutils.Vector((0, 1, 0))
            roll_vec_local = mathutils.Vector((1, 0, 0))
        else: # 'Z'
            y_vec_local = mathutils.Vector((0, 0, 1))
            roll_vec_local = mathutils.Vector((0, 1, 0))

        if is_neg:
            y_vec_local *= -1.0

        # Transform these local direction vectors into world space
        obj_rot_mat = mat.to_3x3()
        y_vec_world = (obj_rot_mat @ y_vec_local).normalized()
        roll_vec_world = (obj_rot_mat @ roll_vec_local).normalized()

        # 3. Calculate length from combined points projected onto the axis
        # Project all world points onto the bone's direction vector
        origin_proj = head_world.dot(y_vec_world)
        projections = [(mat @ p).dot(y_vec_world) for p in all_points_local]
        
        max_extent = max(p - origin_proj for p in projections)

        if max_extent < 0.001:
            length = max(projections) - min(projections)
        else:
            length = max_extent
        
        if length < 0.001: length = 0.01

        tail_world = head_world + length * y_vec_world

    # --- Final Radius Calculation (common for all modes) ---
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
            
    if max_radius < 0.001: max_radius = 0.05

    return head_world, tail_world, roll_vec_world, max_radius

def _process_bones_in_edit_mode(rig: bpy.types.Object, bones_to_create: List[Tuple[str, mathutils.Vector, mathutils.Vector, mathutils.Vector]]) -> None:
    """
    Creates or updates a batch of bones in a single Edit Mode session.

    :param rig: The armature object.
    :param bones_to_create: A list of tuples, each containing
                            (bone_name, head_world, tail_world, roll_vec_world).
    """
    bpy.ops.object.mode_set(mode='EDIT')
    rig_mat_inv = rig.matrix_world.inverted()
    for b_name, head, tail, roll_vec in bones_to_create:
        eb = rig.data.edit_bones.get(b_name) or rig.data.edit_bones.new(b_name)
        eb.head = rig_mat_inv @ head
        eb.tail = rig_mat_inv @ tail
        # --- FIX: The roll vector must be in the armature's local space ---
        # The incoming roll_vec is in world space. We must transform it into the
        # armature's local coordinate system before passing it to align_roll.
        roll_vec_armature = rig_mat_inv.to_3x3() @ roll_vec
        eb.align_roll(roll_vec_armature)

        # AI Editor Note: Removed the forced -90 degree Z-rotation.
        # The user requested that the bone generation should reference the target object's
        # local axis orientation. The previous rotation was offsetting the bone
        # from the calculated alignment (which matches the object's local axes).
        # By removing this, the bone's Y-axis will correctly align with the
        # object's local axis determined in `_calculate_bone_geometry`.

def _process_bones_in_pose_mode(rig: bpy.types.Object, bones_to_process: list, context: bpy.types.Context) -> None:
    """
    Sets properties and parents meshes in a single Pose Mode session.

    :param rig: The armature object.
    :param bones_to_process: A list of dicts, each containing 'name', 'objs_data', 'radius', 'axis'.
                             'objs_data' is a list of (obj, original_matrix).
    :param context: The current Blender context.
    """
    bpy.ops.object.mode_set(mode='POSE')
    for b_info in bones_to_process:
        b_name = b_info['name']
        axis = b_info['axis']
        radius = b_info['radius']
        objs_data = b_info['objs_data']
        
        pbone = rig.pose.bones.get(b_name)
        if pbone:
            # AI Editor Note: Set the bone's axis property to match the alignment axis.
            pbone.urdf_props.axis_enum = 'Z' if axis == 'AUTO' else axis
            pbone.urdf_props.joint_type = 'none'
            pbone.urdf_props.joint_radius = radius
            update_single_bone_gizmo(pbone, context.scene.urdf_viz_gizmos)

            # Parent all meshes in the group to the bone while keeping their world transforms
            for obj, original_matrix in objs_data:
                obj.parent = rig
                obj.parent_type = 'BONE'
                obj.parent_bone = b_name
                obj.matrix_world = original_matrix

class OPS_OT_AddBone(bpy.types.Operator):
    bl_idname = "urdf.add_bone"
    bl_label = "Set / Align Bones"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: bpy.types.Context) -> Set[str]:
        """
        Creates or updates bones based on selected mesh objects.

        AI Editor Note:
        This operator demonstrates a best-practice pattern for writing robust
        Blender operators that perform complex actions. It avoids common errors
        related to changing context (e.g., switching modes) while iterating.
        The process is broken into clear, safe stages:
        1.  **Gather Data**: All necessary information (object geometry, desired
            bone names, etc.) is collected in Object Mode *before* any changes
            are made. This avoids issues with accessing data that might become
            invalid after a mode change.
        2.  **Batch Edit Mode Operations**: The operator switches to Edit Mode
            *once*, creates or updates all bones in a single batch, and then
            switches out.
        3.  **Batch Pose Mode Operations**: It then switches to Pose Mode *once*
            to set all properties, constraints, and parenting relationships.
        4.  **Restore Context**: Finally, it restores the user's original selection
            and active object, providing a seamless user experience.
        """
        # Collect base targets from selection (excluding armatures)
        base_targets = [obj for obj in context.selected_objects if obj.type != 'ARMATURE']
        
        # Helper to gather all descendants recursively
        def gather_recursive(o, obj_set):
            obj_set.add(o)
            for child in o.children:
                gather_recursive(child, obj_set)

        rig = context.scene.urdf_active_rig
        
        # Sub-selection Support: Check for meshes parented to selected pose bones if we are in Pose Mode.
        bone_to_mesh_map = {}
        if context.mode == 'POSE' and context.selected_pose_bones:
            for pbone in context.selected_pose_bones:
                meshes = get_all_children_objects(pbone, context)
                if meshes:
                    bone_to_mesh_map[pbone.name] = meshes
        
        if not base_targets and not bone_to_mesh_map:
            self.report({'WARNING'}, "Select at least one object (or bone with meshes) and set an active rig.")
            return {'CANCELLED'}
            
        if not rig or rig.name not in context.view_layer.objects:
            # Try to get rig from active object if scene property is not set or invalid
            if context.active_object and context.active_object.type == 'ARMATURE':
                rig = context.active_object
            elif context.mode == 'POSE' and context.object and context.object.type == 'ARMATURE':
                rig = context.object
            
            # If still not found, search selected objects for an armature
            if not rig or rig.name not in context.view_layer.objects:
                for obj in context.selected_objects:
                    if obj.type == 'ARMATURE':
                        rig = obj
                        break
            
            # If still not found, search children of selected targets for their parent rig
            if not rig or rig.name not in context.view_layer.objects:
                for obj in base_targets:
                    if obj.parent and obj.parent.type == 'ARMATURE' and obj.parent.name in context.view_layer.objects:
                        rig = obj.parent
                        break

            if not rig or rig.name not in context.view_layer.objects:
                rig_name = rig.name if rig else "None"
                self.report({'ERROR'}, f"Active rig '{rig_name}' not found in current ViewLayer. Select an armature or set it in the Kinematics panel.")
                return {'CANCELLED'}
            
            # Update the scene property to the valid one we found
            context.scene.urdf_active_rig = rig

        # AI Editor Note: Force update to ensure all object matrices are fresh before calculation.
        context.view_layer.update()

        # --- 1. Gather Geometry Data ---
        bones_to_process = []
        axis_for_alignment = context.scene.urdf_bone_axis
        
        if base_targets:
            mode = context.scene.urdf_bone_mode
            groups = [] # List of tuples: (reference_obj, [all_objs_in_group])
            
            if mode == 'SINGLE':
                # All selected objects and their descendants belong to one single group
                all_objects = set()
                for obj in base_targets:
                    gather_recursive(obj, all_objects)
                
                active_obj = context.active_object
                reference = active_obj if active_obj in all_objects else list(all_objects)[0]
                groups.append((reference, list(all_objects)))
            else: # 'INDIVIDUAL'
                # Find top-level selected objects (ignore a selected object if its parent is also selected)
                top_level_targets = []
                for obj in base_targets:
                    curr = obj.parent
                    is_sub_selected = False
                    while curr:
                        if curr in base_targets:
                            is_sub_selected = True
                            break
                        curr = curr.parent
                    if not is_sub_selected:
                        top_level_targets.append(obj)
                
                # Each top-level selected object forms a group along with its full hierarchy
                for root_obj in top_level_targets:
                    group_objs = set()
                    gather_recursive(root_obj, group_objs)
                    groups.append((root_obj, list(group_objs)))
            
            for reference, group_objs in groups:
                head, tail, roll, radius = _calculate_bone_geometry(group_objs, axis_for_alignment, reference)
                # Reuse bone name if already parented
                b_name = reference.parent_bone if reference.parent == rig and reference.parent_type == 'BONE' else f"Bone_{reference.name.replace('.', '_')}"
                
                objs_data = [(o, o.matrix_world.copy()) for o in group_objs]
                bones_to_process.append({
                    'name': b_name, 
                    'head': head, 
                    'tail': tail, 
                    'roll': roll, 
                    'objs_data': objs_data, 
                    'radius': radius, 
                    'axis': axis_for_alignment
                })
        
        if bone_to_mesh_map:
            # Handle bone sub-selection: Align each selected bone to its respective meshes
            for b_name, meshes in bone_to_mesh_map.items():
                if any(b['name'] == b_name for b in bones_to_process):
                    continue
                
                primary_obj = meshes[0]
                head, tail, roll, radius = _calculate_bone_geometry(meshes, axis_for_alignment, primary_obj)
                
                objs_data = [(o, o.matrix_world.copy()) for o in meshes]
                bones_to_process.append({
                    'name': b_name, 
                    'head': head, 
                    'tail': tail, 
                    'roll': roll, 
                    'objs_data': objs_data, 
                    'radius': radius, 
                    'axis': axis_for_alignment
                })

        if not bones_to_process:
            return {'CANCELLED'}

        # --- 3. Perform Operations in Batches ---
        original_mode = rig.mode
        original_active = context.view_layer.objects.active
        
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = rig
        rig.select_set(True)

        # Batch 1: Edit Mode
        edit_mode_data = [(b['name'], b['head'], b['tail'], b['roll']) for b in bones_to_process]
        _process_bones_in_edit_mode(rig, edit_mode_data)

        # Batch 2: Pose Mode
        # AI Editor Note: Force a mode switch to OBJECT and an update first.
        bpy.ops.object.mode_set(mode='OBJECT')
        context.view_layer.update()
        
        _process_bones_in_pose_mode(rig, bones_to_process, context)

        # --- 4. Switch to Pose Mode ---
        context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='POSE')
        
        self.report({'INFO'}, f"Processed {len(bones_to_process)} bones.")
        return {'FINISHED'}

class URDF_OT_ApplyRestPose(bpy.types.Operator):
    """Applies the current pose as the new rest pose for the entire armature, updating all drivers to maintain relationships."""
    bl_idname = "urdf.apply_rest_pose"
    bl_label = "Apply as Rest Pose"
    bl_description = "Apply current pose as rest pose (Armature) and apply Scale/Rotation (Meshes)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene.urdf_active_rig is not None or len(context.selected_objects) > 0

    def execute(self, context: bpy.types.Context) -> Set[str]:
        # 1. Apply Scale & Rotation to selected Mesh objects (including sub-selected hierarchies)
        all_meshes = set()
        def gather_meshes(o):
            if o.type == 'MESH':
                all_meshes.add(o)
            for child in o.children:
                gather_meshes(child)
        for obj in context.selected_objects:
            gather_meshes(obj)
        selected_meshes = list(all_meshes)
        if selected_meshes:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            self.report({'INFO'}, f"Applied transforms to {len(selected_meshes)} meshes.")

        # 2. Apply Rest Pose to Active Rig
        rig = context.scene.urdf_active_rig
        if rig and rig.name in context.view_layer.objects:
            prev_mode = context.mode
            prev_active = context.view_layer.objects.active
            
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = rig
            rig.select_set(True)
            bpy.ops.object.mode_set(mode='POSE')

            bpy.ops.pose.armature_apply(selected=False)

            for bone in rig.pose.bones:
                if hasattr(bone, 'urdf_props') and bone.urdf_props.mimic_drivers:
                    for mimic in bone.urdf_props.mimic_drivers:
                        core.add_native_driver_relation(bone, mimic.target_bone, mimic.ratio, bone.urdf_props.ratio_invert)
            
            bpy.ops.object.mode_set(mode='OBJECT')
            if prev_active and prev_active.name in context.view_layer.objects:
                context.view_layer.objects.active = prev_active
                prev_active.select_set(True)
            for m in selected_meshes:
                m.select_set(True)
            if prev_mode == 'POSE' and prev_active == rig:
                bpy.ops.object.mode_set(mode='POSE')

            self.report({'INFO'}, "Applied Rest Pose to Armature.")
            
        return {'FINISHED'}
# ------------------------------------------------------------------------

class URDF_OT_LightTarget(bpy.types.Operator):
    """
    Constrains selected lights to point specifically at the last selected object center.
    AI Editor Note: This uses a Damped Track constraint to ensure the light follows 
    the target dynamically as it moves.
    """
    bl_idname = "urdf.light_target"
    bl_label = "Target Active Object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        props = context.scene.urdf_lighting_props
        # Enabled if eyedropper has target OR anything is selected in viewport
        return (props.selected_light_target is not None or 
                len(context.selected_objects) >= 1)

    def execute(self, context):
        props = context.scene.urdf_lighting_props
        # Priority 1: Eyedropper target
        # Priority 2: Active object
        target = props.selected_light_target or context.active_object
        
        if not target:
            self.report({'ERROR'}, "Select a target via eyedropper or pick one in the viewport.")
            return {'CANCELLED'}

        count = 0
        for obj in context.selected_objects:
            if obj == target or obj.type != 'LIGHT':
                continue
            
            # Remove existing tracking if any
            for c in obj.constraints:
                if c.type in ['DAMPED_TRACK', 'TRACK_TO']:
                    obj.constraints.remove(c)
            
            # Add Damped Track
            # -Z is the standard direction for Blender lights (Spot, Area, Sun)
            dt = obj.constraints.new('DAMPED_TRACK')
            dt.target = target
            dt.track_axis = 'TRACK_NEGATIVE_Z'
            count += 1

        self.report({'INFO'}, f"Targeted {count} lights to {target.name}")
        return {'FINISHED'}

class URDF_OT_ApplyToonShader(bpy.types.Operator):
    """
    Applies a 'Shader to RGB' node setup to selected objects to remove light gradients.
    Note: Requires EEVEE renderer to work properly.
    """
    bl_idname = "urdf.apply_toon_shader"
    bl_label = "Apply Toon Shader"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(o.type == 'MESH' for o in context.selected_objects)

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH': continue
            
            # Ensure at least one material slot exists
            if not obj.material_slots:
                obj.data.materials.append(bpy.data.materials.new(name="Toon_Material"))
            
            for slot in obj.material_slots:
                mat = slot.material
                if not mat:
                    mat = bpy.data.materials.new(name="Toon_Material")
                    slot.material = mat
                
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                
                # Avoid duplicates
                if any(n.name == "Toon_ColorRamp" for n in nodes):
                    count += 1
                    continue
                
                # Get Output or create one
                output_node = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if not output_node:
                    output_node = nodes.new('ShaderNodeOutputMaterial')
                    output_node.location = (400, 0)
                
                # Find a shader to work with - find existing link or create Principled BSDF
                source_socket = None
                surface_input = output_node.inputs['Surface']
                
                if surface_input.links:
                    source_socket = surface_input.links[0].from_socket
                else:
                    shader_node = next((n for n in nodes if n.type in {'BSDF_PRINCIPLED', 'BSDF_DIFFUSE'}), None)
                    if not shader_node:
                        shader_node = nodes.new('ShaderNodeBsdfPrincipled')
                        shader_node.location = (-800, 0)
                    source_socket = shader_node.outputs[0]
                
                if not source_socket: continue
                
                # --- TOON MASTER SETUP ---
                # 1. Shader to RGB (Captures Light/Shadow Data)
                s_to_rgb = nodes.new('ShaderNodeShaderToRGB')
                s_to_rgb.location = (output_node.location.x - 700, output_node.location.y)
                
                # 2. Color Ramp (The Hard Terminator with 30% shadow floor)
                ramp = nodes.new('ShaderNodeValToRGB')
                ramp.name = "Toon_ColorRamp"
                ramp.label = "Toon Mask"
                ramp.location = (output_node.location.x - 450, output_node.location.y)
                ramp.color_ramp.interpolation = 'CONSTANT'
                
                # First stop: 30% visibility for ambient detail
                ramp.color_ramp.elements[0].color = (0.3, 0.3, 0.3, 1.0)
                ramp.color_ramp.elements[0].position = 0.5
                
                # Second stop: 100% visibility for lit areas
                ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
                
                # 3. Mix (Multiply Light Mask with Base Color)
                mix = nodes.new('ShaderNodeMix')
                mix.data_type = 'RGBA'
                mix.blend_type = 'MULTIPLY'
                mix.location = (output_node.location.x - 200, output_node.location.y)
                mix.inputs[0].default_value = 1.0 # Factor 100%
                
                # Check for existing color nodes to plug into A
                base_color_node = next((n for n in nodes if n.type == 'RGB' or n.name == "Base Color"), None)
                if base_color_node:
                    links.new(base_color_node.outputs[0], mix.inputs[6])
                else:
                    mix.inputs[6].default_value = (1.0, 1.0, 1.0, 1.0)

                # --- Link the chain ---
                links.new(source_socket, s_to_rgb.inputs[0])
                links.new(s_to_rgb.outputs[0], ramp.inputs[0])
                links.new(ramp.outputs[0], mix.inputs[7]) # Slot B
                links.new(mix.outputs[2], surface_input)
                
                count += 1
                
        self.report({'INFO'}, f"Applied Ambient-Friendly Toon setup to {count} materials.")
        return {'FINISHED'}

class URDF_OT_GlobalToonSharpness(bpy.types.Operator):
    """
    Sets all lights in the scene to sharp shadows and zero specular for tooning.
    """
    bl_idname = "urdf.global_toon_sharpness"
    bl_label = "Set Global Sharpness"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(
        items=[('TOON', "Toon", ""), ('REALISTIC', "Realistic", "")]
    )

    def execute(self, context):
        count = 0
        for light in bpy.data.lights:
            if self.mode == 'TOON':
                if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.0
                if hasattr(light, 'radius'): light.radius = 0.0
                if hasattr(light, 'angle'): light.angle = 0.0
                if hasattr(light, 'specular_factor'): light.specular_factor = 0.0
                if hasattr(light, 'shadow_buffer_bias'): light.shadow_buffer_bias = 0.1
                if hasattr(light, 'use_contact_shadow'): light.use_contact_shadow = True
            else:
                if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.1
                if hasattr(light, 'radius'): light.radius = 0.2
                if hasattr(light, 'angle'): light.angle = 0.1
                if hasattr(light, 'specular_factor'): light.specular_factor = 1.0
                if hasattr(light, 'shadow_buffer_bias'): light.shadow_buffer_bias = 0.05
                if hasattr(light, 'use_contact_shadow'): light.use_contact_shadow = False
            count += 1
            
        self.report({'INFO'}, f"Updated {count} lights to {self.mode.lower()} mode.")
        return {'FINISHED'}

class URDF_OT_ToonifySelectedLights(bpy.types.Operator):
    """
    Sets selected light sources to sharp 'Toon' style lighting.
    """
    bl_idname = "urdf.toonify_selected_lights"
    bl_label = "Toonify Selected Lights"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'LIGHT':
                light = obj.data
                if hasattr(light, 'shadow_soft_size'): light.shadow_soft_size = 0.0
                if hasattr(light, 'radius'): light.radius = 0.0
                if hasattr(light, 'specular_factor'): light.specular_factor = 0.0
                if hasattr(light, 'shadow_buffer_bias'): light.shadow_buffer_bias = 0.1
                if hasattr(light, 'use_contact_shadow'): light.use_contact_shadow = True
                if hasattr(light, 'spot_blend'): light.spot_blend = 0.0
                count += 1
        
        self.report({'INFO'}, f"Toonified {count} light sources.")
        return {'FINISHED'}

def register():
    CLASSES = [
        URDF_OT_OpenAssetBrowser, URDF_OT_RegisterAssetCategory, URDF_OT_MarkAndUploadAsset, URDF_OT_ImportToAssetCategory,
        URDF_OT_LightTarget, URDF_OT_ApplyToonShader, URDF_OT_GlobalToonSharpness, URDF_OT_ToonifySelectedLights, 
        OPS_OT_Execute_AI_Prompt, URDF_OT_Generate_Preset, URDF_OT_SetJointType, OPS_OT_CalculateCenterOfMass, 
        OPS_OT_CalculateInertia, OPS_OT_BakeMesh, URDF_OT_ReadJointSettings, URDF_OT_ApplyJointSettings, 
        OPS_OT_SetupIK, OPS_OT_SetOriginToCursor, URDF_OT_Material_AddSmart, URDF_OT_Material_LoadTexture, 
        URDF_OT_Material_FromImage, URDF_OT_AddMappingNodes, URDF_OT_UV_SmartUnwrap, URDF_OT_Material_Merge, 
        URDF_OT_Material_Add, URDF_UL_Mat_List, URDF_UL_SlinkyHooks_List, URDF_OT_Paint_SetupBrush, 
        OPS_OT_ExportGazeboWorld, OPS_OT_LinkChainDriver, OPS_OT_AddBoolean, URDF_OT_AddParametricAnchor, 
        URDF_OT_AddMarker, URDF_OT_ToggleHookPlacement, URDF_OT_CleanupAnchor, URDF_OT_BakeAnchor, 
        URDF_OT_AddTextDescription, URDF_OT_RemoveDimension, URDF_OT_AddDimension, OPS_OT_AddModifier, 
        OPS_OT_AddSimplify, OPS_OT_SetupLinearArray, OPS_OT_SetupRadialArray, OPS_OT_CreateCurveForPath, 
        OPS_OT_SetupCurveArray, OPS_OT_SmartSmooth, OPS_OT_CreatePart, OPS_OT_ChainAddWrapObject, 
        OPS_OT_CreateElectronicPart, OPS_OT_ChainAddPickedWrapObject, OPS_OT_ChainRemoveWrapObject, 
        URDF_OT_SlinkyAddHook, URDF_OT_SlinkyRemoveHook, OPS_OT_CalculateRatio, OPS_OT_AddMimic, 
        OPS_OT_RemoveMimic, OPS_OT_ClearConfig, OPS_OT_ApplyBoneConstraints, OPS_OT_PickBone, 
        URDF_OT_GenerateROS2Workspace, URDF_ExportItem, URDF_UL_ExportList, URDF_OT_ExportList_Add, 
        URDF_OT_ExportList_Remove, OPS_OT_Export, URDF_OT_ExportSelected, OPS_OT_TogglePlacement, 
        OPS_OT_CreateRig, URDF_OT_MergeArmatures, URDF_OT_PurgeBones, OPS_OT_ParentToActive, 
        OPS_OT_EnterPoseMode, OPS_OT_EnterObjectMode, OPS_OT_AddBone, URDF_OT_ApplyRestPose
    ]
    for cls in CLASSES:
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

def unregister():
    CLASSES = [
        URDF_OT_OpenAssetBrowser, URDF_OT_RegisterAssetCategory, URDF_OT_MarkAndUploadAsset, URDF_OT_ImportToAssetCategory,
        URDF_OT_LightTarget, URDF_OT_ApplyToonShader, URDF_OT_GlobalToonSharpness, URDF_OT_ToonifySelectedLights, 
        OPS_OT_Execute_AI_Prompt, URDF_OT_Generate_Preset, URDF_OT_SetJointType, OPS_OT_CalculateCenterOfMass, 
        OPS_OT_CalculateInertia, OPS_OT_BakeMesh, URDF_OT_ReadJointSettings, URDF_OT_ApplyJointSettings, 
        OPS_OT_SetupIK, OPS_OT_SetOriginToCursor, URDF_OT_Material_AddSmart, URDF_OT_Material_LoadTexture, 
        URDF_OT_Material_FromImage, URDF_OT_AddMappingNodes, URDF_OT_UV_SmartUnwrap, URDF_OT_Material_Merge, 
        URDF_OT_Material_Add, URDF_UL_Mat_List, URDF_UL_SlinkyHooks_List, URDF_OT_Paint_SetupBrush, 
        OPS_OT_ExportGazeboWorld, OPS_OT_LinkChainDriver, OPS_OT_AddBoolean, URDF_OT_AddParametricAnchor, 
        URDF_OT_AddMarker, URDF_OT_ToggleHookPlacement, URDF_OT_CleanupAnchor, URDF_OT_BakeAnchor, 
        URDF_OT_AddTextDescription, URDF_OT_RemoveDimension, URDF_OT_AddDimension, OPS_OT_AddModifier, 
        OPS_OT_AddSimplify, OPS_OT_SetupLinearArray, OPS_OT_SetupRadialArray, OPS_OT_CreateCurveForPath, 
        OPS_OT_SetupCurveArray, OPS_OT_SmartSmooth, OPS_OT_CreatePart, OPS_OT_ChainAddWrapObject, 
        OPS_OT_CreateElectronicPart, OPS_OT_ChainAddPickedWrapObject, OPS_OT_ChainRemoveWrapObject, 
        URDF_OT_SlinkyAddHook, URDF_OT_SlinkyRemoveHook, OPS_OT_CalculateRatio, OPS_OT_AddMimic, 
        OPS_OT_RemoveMimic, OPS_OT_ClearConfig, OPS_OT_ApplyBoneConstraints, OPS_OT_PickBone, 
        URDF_OT_GenerateROS2Workspace, URDF_ExportItem, URDF_UL_ExportList, URDF_OT_ExportList_Add, 
        URDF_OT_ExportList_Remove, OPS_OT_Export, URDF_OT_ExportSelected, OPS_OT_TogglePlacement, 
        OPS_OT_CreateRig, URDF_OT_MergeArmatures, URDF_OT_PurgeBones, OPS_OT_ParentToActive, 
        OPS_OT_EnterPoseMode, OPS_OT_EnterObjectMode, OPS_OT_AddBone, URDF_OT_ApplyRestPose
    ]
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
