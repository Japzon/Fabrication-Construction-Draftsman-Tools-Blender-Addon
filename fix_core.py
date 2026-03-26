# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import sys
import os

path = r'c:\Users\japzo\OneDrive\Desktop\Blender Add-on Workshop\Fabrication-Construction-Draftsman-Tools-Automated\core.py'
with open(path, 'r') as f:
    content = f.read()

# Replace setup_native_rope_gn
start_marker = 'def setup_native_rope_gn(rope_obj: bpy.types.Object) -> None:'
end_marker = 'def setup_native_wrap_gn('
start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_func = """def setup_native_rope_gn(rope_obj: bpy.types.Object) -> None:
    \"\"\"
    High-Fidelity Rope Generator.
    Stabilized for Blender 4.x with proper group interface lookups.
    \"\"\"
    gn_group_name = f'URDF_Native_{rope_obj.name}_Rope_GN'
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')
        iface = gn_group.interface
        
        # Sockets
        iface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
        iface.new_socket(name='Total Radius', in_out='INPUT', socket_type='NodeSocketFloat')
        iface.new_socket(name='Strands', in_out='INPUT', socket_type='NodeSocketInt')
        iface.new_socket(name='Twist Rate', in_out='INPUT', socket_type='NodeSocketFloat')
        iface.new_socket(name='Tube Mode', in_out='INPUT', socket_type='NodeSocketBool')
        iface.new_socket(name='Is Synthetic', in_out='INPUT', socket_type='NodeSocketBool')
        iface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')

        nodes, links = gn_group.nodes, gn_group.links
        g_in, g_out = nodes.new('NodeGroupInput'), nodes.new('NodeGroupOutput')
        
        # Path Prep
        m_to_c = nodes.new('GeometryNodeMeshToCurve')
        resam = nodes.new('GeometryNodeResampleCurve'); resam.mode = 'LENGTH'; resam.inputs['Length'].default_value = 0.002
        dup = nodes.new('GeometryNodeDuplicateElements'); dup.domain = 'SPLINE'
        para, idx = nodes.new('GeometryNodeSplineParameter'), nodes.new('GeometryNodeInputIndex')

        # Packing
        import math
        m_pi = nodes.new('ShaderNodeMath'); m_pi.operation = 'DIVIDE'; m_pi.inputs[0].default_value = math.pi
        m_sin_a = nodes.new('ShaderNodeMath'); m_sin_a.operation = 'SINE'
        m_plus = nodes.new('ShaderNodeMath'); m_plus.operation = 'ADD'; m_plus.inputs[1].default_value = 1.0
        m_ring_r = nodes.new('ShaderNodeMath'); m_ring_r.operation = 'DIVIDE'
        m_strand_r = nodes.new('ShaderNodeMath'); m_strand_r.operation = 'MULTIPLY'
        
        # Link Packing
        links.new(g_in.outputs['Strands'], m_pi.inputs[1]); links.new(m_pi.outputs[0], m_sin_a.inputs[0])
        links.new(m_sin_a.outputs[0], m_plus.inputs[0]); links.new(m_plus.outputs[0], m_ring_r.inputs[1])
        links.new(g_in.outputs['Total Radius'], m_ring_r.inputs[0])
        links.new(m_ring_r.outputs[0], m_strand_r.inputs[0]); links.new(m_sin_a.outputs[0], m_strand_r.inputs[1])

        # Twist Math
        m_2pi = nodes.new('ShaderNodeMath'); m_2pi.operation = 'MULTIPLY'; m_2pi.inputs[0].default_value = math.pi*2
        m_angle_unit = nodes.new('ShaderNodeMath'); m_angle_unit.operation = 'DIVIDE'
        m_base_angle = nodes.new('ShaderNodeMath'); m_base_angle.operation = 'MULTIPLY'
        m_twist_acc = nodes.new('ShaderNodeMath'); m_twist_acc.operation = 'MULTIPLY'
        
        # Link Angle
        links.new(g_in.outputs['Strands'], m_angle_unit.inputs[1]); links.new(m_2pi.outputs[0], m_angle_unit.inputs[0])
        links.new(m_angle_unit.outputs[0], m_base_angle.inputs[0]); links.new(idx.outputs['Index'], m_base_angle.inputs[1])
        links.new(g_in.outputs['Twist Rate'], m_twist_acc.inputs[1]); links.new(para.outputs['Factor'], m_twist_acc.inputs[0])
        
        # Braiding
        m_lay_sw = nodes.new('GeometryNodeSwitch'); m_lay_sw.input_type = 'FLOAT'; m_lay_sw.inputs['False'].default_value = 1.0
        m_mod2 = nodes.new('ShaderNodeMath'); m_mod2.operation = 'MODULO'; m_mod2.inputs[1].default_value = 2.0
        m_dir = nodes.new('ShaderNodeMath'); m_dir.operation = 'MULTIPLY'; m_dir.inputs[1].default_value = -2.0
        m_dir_add = nodes.new('ShaderNodeMath'); m_dir_add.operation = 'ADD'; m_dir_add.inputs[1].default_value = 1.0
        m_tw_mult = nodes.new('ShaderNodeMath'); m_tw_mult.operation = 'MULTIPLY'
        m_total_angle = nodes.new('ShaderNodeMath'); m_total_angle.operation = 'ADD'
        
        links.new(idx.outputs['Index'], m_mod2.inputs[0]); links.new(m_mod2.outputs[0], m_dir.inputs[0])
        links.new(m_dir.outputs[0], m_dir_add.inputs[0]); links.new(m_dir_add.outputs[0], m_lay_sw.inputs['True'])
        links.new(g_in.outputs['Is Synthetic'], m_lay_sw.inputs['Switch'])
        links.new(m_twist_acc.outputs[0], m_tw_mult.inputs[0]); links.new(m_lay_sw.outputs[0], m_tw_mult.inputs[1])
        links.new(m_base_angle.outputs[0], m_total_angle.inputs[0]); links.new(m_tw_mult.outputs[0], m_total_angle.inputs[1])

        # Frenet Orientation
        tan_v, norm_v = nodes.new('GeometryNodeInputTangent'), nodes.new('GeometryNodeInputNormal')
        binorm_v = nodes.new('ShaderNodeVectorMath'); binorm_v.operation = 'CROSS_PRODUCT'
        links.new(tan_v.outputs[0], binorm_v.inputs[0]); links.new(norm_v.outputs[0], binorm_v.inputs[1])

        m_cos, m_sin = nodes.new('ShaderNodeMath'), nodes.new('ShaderNodeMath')
        m_cos.operation, m_sin.operation = 'COSINE', 'SINE'
        m_rcos, m_rsin = nodes.new('ShaderNodeMath'), nodes.new('ShaderNodeMath')
        m_rcos.operation, m_rsin.operation = 'MULTIPLY', 'MULTIPLY'
        v_off_n, v_off_b = nodes.new('ShaderNodeVectorMath'), nodes.new('ShaderNodeVectorMath')
        v_off_n.operation, v_off_b.operation = 'SCALE', 'SCALE'
        v_sum = nodes.new('ShaderNodeVectorMath'); v_sum.operation = 'ADD'
        
        links.new(m_total_angle.outputs[0], m_cos.inputs[0]); links.new(m_total_angle.outputs[0], m_sin.inputs[0])
        links.new(m_ring_r.outputs[0], m_rcos.inputs[0]); links.new(m_cos.outputs[0], m_rcos.inputs[1])
        links.new(m_ring_r.outputs[0], m_rsin.inputs[0]); links.new(m_sin.outputs[0], m_rsin.inputs[1])
        links.new(norm_v.outputs[0], v_off_n.inputs['Vector']); links.new(m_rcos.outputs[0], v_off_n.inputs['Scale'])
        links.new(binorm_v.outputs[0], v_off_b.inputs['Vector']); links.new(m_rsin.outputs[0], v_off_b.inputs['Scale'])
        links.new(v_off_n.outputs[0], v_sum.inputs[0]); links.new(v_off_b.outputs[0], v_sum.inputs[1])
        
        # Offset Application
        set_pos = nodes.new('GeometryNodeSetPosition')
        links.new(dup.outputs['Geometry'], set_pos.inputs['Geometry']); links.new(v_sum.outputs[0], set_pos.inputs['Offset'])
        
        # Mesh Generation
        links.new(g_in.outputs['Geometry'], m_to_c.inputs['Mesh']); links.new(m_to_c.outputs['Curve'], resam.inputs['Curve'])
        links.new(resam.outputs['Curve'], dup.inputs['Geometry'])
        links.new(g_in.outputs['Strands'], dup.inputs['Amount'])
        
        prof_c = nodes.new('GeometryNodeCurvePrimitiveCircle'); prof_c.inputs['Resolution'].default_value = 32
        sweep = nodes.new('GeometryNodeCurveToMesh')
        links.new(set_pos.outputs['Geometry'], sweep.inputs['Curve']); links.new(prof_c.outputs['Curve'], sweep.inputs['Profile Curve'])
        links.new(m_strand_r.outputs[0], prof_c.inputs['Radius'])

        # Core
        comp_core = nodes.new('FunctionNodeCompare'); comp_core.data_type = 'INT'; comp_core.operation = 'GREATER_EQUAL'; comp_core.inputs['B'].default_value = 5
        m_not_synth = nodes.new('ShaderNodeMath'); m_not_synth.operation = 'SUBTRACT'; m_not_synth.inputs[0].default_value = 1.0
        m_use_core = nodes.new('ShaderNodeMath'); m_use_core.operation = 'MULTIPLY'
        sw_core = nodes.new('GeometryNodeSwitch'); sw_core.input_type = 'GEOMETRY'
        core_sweep = nodes.new('GeometryNodeCurveToMesh'); core_prof = nodes.new('GeometryNodeCurvePrimitiveCircle'); core_prof.inputs['Resolution'].default_value = 32
        
        links.new(g_in.outputs['Strands'], comp_core.inputs['A']); links.new(g_in.outputs['Is Synthetic'], m_not_synth.inputs[1])
        links.new(comp_core.outputs[0], m_use_core.inputs[0]); links.new(m_not_synth.outputs[0], m_use_core.inputs[1])
        links.new(m_use_core.outputs[0], sw_core.inputs['Switch'])
        links.new(resam.outputs['Curve'], core_sweep.inputs['Curve']); links.new(core_prof.outputs['Curve'], core_sweep.inputs['Profile Curve'])
        links.new(m_strand_r.outputs[0], core_prof.inputs['Radius']); links.new(core_sweep.outputs['Mesh'], sw_core.inputs['True'])

        # Tube Swapper & Final Material
        join = nodes.new('GeometryNodeJoinGeometry')
        sw_tube = nodes.new('GeometryNodeSwitch'); sw_tube.input_type = 'GEOMETRY'
        tube_prof = nodes.new('GeometryNodeCurvePrimitiveCircle'); tube_prof.inputs['Resolution'].default_value = 32
        tube_sweep = nodes.new('GeometryNodeCurveToMesh'); set_mat = nodes.new('GeometryNodeSetMaterial')

        links.new(sweep.outputs['Mesh'], join.inputs[0]); links.new(sw_core.outputs[0], join.inputs[0])
        links.new(resam.outputs['Curve'], tube_sweep.inputs['Curve']); links.new(tube_prof.outputs['Curve'], tube_sweep.inputs['Profile Curve'])
        links.new(g_in.outputs['Total Radius'], tube_prof.inputs['Radius'])
        links.new(g_in.outputs['Tube Mode'], sw_tube.inputs['Switch'])
        links.new(join.outputs['Geometry'], sw_tube.inputs['False']); links.new(tube_sweep.outputs['Mesh'], sw_tube.inputs['True'])
        links.new(sw_tube.outputs[0], set_mat.inputs['Geometry']); links.new(set_mat.outputs['Geometry'], g_out.inputs[0])

    # Modifiers & Drivers
    if hasattr(rope_obj.data, 'twist_mode'): rope_obj.data.twist_mode = 'MINIMUM'
    mod = rope_obj.modifiers.get(f'{MOD_PREFIX}Native_Rope')
    if not mod: mod = rope_obj.modifiers.new(name=f'{MOD_PREFIX}Native_Rope', type='NODES')
    mod.node_group = gn_group
    
    mapping = {'Total Radius': 'rope_radius', 'Strands': 'rope_strands', 'Twist Rate': 'rope_twist', 'Tube Mode': 'rope_tube_mode', 'Is Synthetic': 'rope_is_synthetic'}
    for in_name, p_name in mapping.items():
        sock = next((s for s in gn_group.interface.inputs if s.name == in_name), None)
        if sock: create_driver(rope_obj, f'["{p_name}"]', mod.name, sock.identifier)
"""
    content = content[:start_idx] + new_func + '\n' + content[end_idx:]
    
    # Also update ROPE categories scaling logic
    # Find category == 'ROPE' block
    search_str = "elif category == 'ROPE':"
    cat_idx = content.find(search_str)
    if cat_idx != -1:
        # Find next # --- 6. Final Regeneration ---
        end_cat_idx = content.find("# --- 6. Final Regeneration ---", cat_idx)
        if end_cat_idx != -1:
            new_cat_logic = \"\"\"elif category == 'ROPE':
        # Default construction: 3-strand steel wire or 6-strand synthetic braid
        if type_sub == 'ROPE_STEEL':
            props.rope_strands = 3
            props.rope_is_synthetic = False
        elif type_sub == 'ROPE_SYNTHETIC':
            props.rope_strands = 6
            props.rope_is_synthetic = True
        elif type_sub == 'ROPE_TUBE':
            props.rope_tube_mode = True
        
        multiplier = scale_factor / 0.1
        props.rope_radius = 0.01 * multiplier
        props.rope_twist = 12.0
    
    \"\"\"
            content = content[:cat_idx] + new_cat_logic + content[end_cat_idx:]

    with open(path, 'w') as f:
        f.write(content)
    print("Update Success")
else:
    print("Indices not found")

