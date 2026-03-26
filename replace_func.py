# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import ast

def replace_function(file_path, func_name, new_func_code):
    with open(file_path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    new_node = ast.parse(new_func_code).body[0]

    found = False
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            tree.body[i] = new_node
            found = True
            break
    
    if not found:
        print(f"Function {func_name} not found")
        return

    new_code = ast.unparse(tree)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_code)

if __name__ == "__main__":
    new_body = r'''
def setup_native_rope_gn(rope_obj):
    """
    Creates a dynamic Geometry Nodes setup for a physics-enabled rope.
    Generates either a tube or twisted strands along the deformed mesh.
    """
    gn_group_name = f"URDF_Native_{rope_obj.name}_Rope_GN"
    gn_group = bpy.data.node_groups.get(gn_group_name)

    if not gn_group:
        gn_group = bpy.data.node_groups.new(name=gn_group_name, type='GeometryNodeTree')
        
        # --- Interface ---
        iface = gn_group.interface
        iface.new_socket(name="Geometry", in_out="INPUT", socket_type='NodeSocketGeometry')
        rad_sock = iface.new_socket(name="Radius", in_out="INPUT", socket_type='NodeSocketFloat')
        rad_sock.default_value = 0.01; rad_sock.min_value = 0.001
        strands_sock = iface.new_socket(name="Strands", in_out="INPUT", socket_type='NodeSocketInt')
        strands_sock.default_value = 6; strands_sock.min_value = 1
        twist_sock = iface.new_socket(name="Twist", in_out="INPUT", socket_type='NodeSocketFloat')
        twist_sock.default_value = 10.0
        tube_sock = iface.new_socket(name="Tube Mode", in_out="INPUT", socket_type='NodeSocketBool')
        synth_sock = iface.new_socket(name="Synthetic", in_out="INPUT", socket_type='NodeSocketBool')
        tube_sock.default_value = False
        iface.new_socket(name="Geometry", in_out="OUTPUT", socket_type='NodeSocketGeometry')

        nodes = gn_group.nodes
        links = gn_group.links
        
        # --- 1. Sockets & Inputs ---
        g_in = nodes.new('NodeGroupInput')
        g_out = nodes.new('NodeGroupOutput')
        
        # --- 2. Path Prep ---
        mesh_to_curve = nodes.new('GeometryNodeMeshToCurve')
        resample = nodes.new('GeometryNodeResampleCurve')
        resample.inputs['Count'].default_value = 128
        
        spline_param = nodes.new('GeometryNodeSplineParameter')
        curve_norm = nodes.new('GeometryNodeInputCurveNormal')
        curve_tangent = nodes.new('GeometryNodeInputTangent')
        
        # --- 3. Strand Duplication ---
        dup_elements = nodes.new('GeometryNodeDuplicateElements')
        dup_elements.domain = 'SPLINE'
        strand_idx = nodes.new('GeometryNodeInputIndex')
        
        # --- 4. Helix Math ---
        math_mod2 = nodes.new('ShaderNodeMath'); math_mod2.operation = 'MODULO'; math_mod2.inputs[1].default_value = 2.0
        math_sign = nodes.new('ShaderNodeMath'); math_sign.operation = 'MULTIPLY'; math_sign.inputs[1].default_value = -2.0
        math_sign_final = nodes.new('ShaderNodeMath'); math_sign_final.operation = 'ADD'; math_sign_final.inputs[1].default_value = 1.0
        switch_sign = nodes.new('GeometryNodeSwitch'); switch_sign.input_type = 'FLOAT'
        switch_sign.inputs[1].default_value = 1.0
        
        math_idx_fac = nodes.new('ShaderNodeMath'); math_idx_fac.operation = 'DIVIDE'
        math_base_angle = nodes.new('ShaderNodeMath'); math_base_angle.operation = 'MULTIPLY'; math_base_angle.inputs[1].default_value = 2.0 * math.pi
        
        math_2pi = nodes.new('ShaderNodeMath'); math_2pi.operation = 'MULTIPLY'; math_2pi.inputs[1].default_value = 2.0 * math.pi
        math_twist_sum = nodes.new('ShaderNodeMath'); math_twist_sum.operation = 'MULTIPLY'
        math_twist_angle = nodes.new('ShaderNodeMath'); math_twist_angle.operation = 'MULTIPLY'
        
        math_total_angle = nodes.new('ShaderNodeMath'); math_total_angle.operation = 'ADD'
        math_cos = nodes.new('ShaderNodeMath'); math_cos.operation = 'COSINE'
        math_sin = nodes.new('ShaderNodeMath'); math_sin.operation = 'SINE'
        
        # --- 5. Weave ---
        math_weave_pi = nodes.new('ShaderNodeMath'); math_weave_pi.operation = 'MULTIPLY'; math_weave_pi.inputs[1].default_value = math.pi
        math_weave_turns = nodes.new('ShaderNodeMath'); math_weave_turns.operation = 'MULTIPLY'; math_weave_turns.inputs[1].default_value = 4.0 * math.pi
        math_weave_sum = nodes.new('ShaderNodeMath'); math_weave_sum.operation = 'ADD'
        math_weave_sin = nodes.new('ShaderNodeMath'); math_weave_sin.operation = 'SINE'
        math_weave_fac = nodes.new('ShaderNodeMath'); math_weave_fac.operation = 'MULTIPLY'; math_weave_fac.inputs[1].default_value = 0.2
        math_weave_off = nodes.new('ShaderNodeMath'); math_weave_off.operation = 'MULTIPLY'
        switch_weave = nodes.new('GeometryNodeSwitch'); switch_weave.input_type = 'FLOAT'
        switch_weave.inputs[1].default_value = 0.0
        
        math_final_r_off = nodes.new('ShaderNodeMath'); math_final_r_off.operation = 'ADD'
        
        # --- 6. Radius Math ---
        math_pi_n = nodes.new('ShaderNodeMath'); math_pi_n.operation = 'DIVIDE'; math_pi_n.inputs[0].default_value = math.pi
        math_sin_n = nodes.new('ShaderNodeMath'); math_sin_n.operation = 'SINE'
        math_f_add1 = nodes.new('ShaderNodeMath'); math_f_add1.operation = 'ADD'; math_f_add1.inputs[1].default_value = 1.0
        math_f_div = nodes.new('ShaderNodeMath'); math_f_div.operation = 'DIVIDE'
        math_strand_r = nodes.new('ShaderNodeMath'); math_strand_r.operation = 'MULTIPLY'
        math_ring_r = nodes.new('ShaderNodeMath'); math_ring_r.operation = 'SUBTRACT'
        
        # --- 7. Position ---
        vec_binormal = nodes.new('ShaderNodeVectorMath'); vec_binormal.operation = 'CROSS_PRODUCT'
        math_rcos = nodes.new('ShaderNodeMath'); math_rcos.operation = 'MULTIPLY'
        math_rsin = nodes.new('ShaderNodeMath'); math_rsin.operation = 'MULTIPLY'
        vec_norm_off = nodes.new('ShaderNodeVectorMath'); vec_norm_off.operation = 'SCALE'
        vec_binorm_off = nodes.new('ShaderNodeVectorMath'); vec_binorm_off.operation = 'SCALE'
        vec_total_off = nodes.new('ShaderNodeVectorMath'); vec_total_off.operation = 'ADD'
        set_pos = nodes.new('GeometryNodeSetPosition')
        
        # --- 8. Mesh ---
        prof_strand = nodes.new('GeometryNodeCurvePrimitiveCircle'); prof_strand.inputs['Resolution'].default_value = 16
        curve_to_mesh = nodes.new('GeometryNodeCurveToMesh')
        prof_tube = nodes.new('GeometryNodeCurvePrimitiveCircle'); prof_tube.inputs['Resolution'].default_value = 16
        curve_to_tube = nodes.new('GeometryNodeCurveToMesh')
        switch_mode = nodes.new('GeometryNodeSwitch'); switch_mode.input_type = 'GEOMETRY'
        set_mat = nodes.new('GeometryNodeSetMaterial')
        
        # --- LINKS ---
        links.new(g_in.outputs['Geometry'], mesh_to_curve.inputs[0])
        links.new(mesh_to_curve.outputs[0], resample.inputs[0])
        links.new(resample.outputs[0], dup_elements.inputs[0])
        links.new(g_in.outputs['Strands'], dup_elements.inputs[1])
        links.new(g_in.outputs['Strands'], math_pi_n.inputs[1])
        links.new(math_pi_n.outputs[0], math_sin_n.inputs[0])
        links.new(math_sin_n.outputs[0], math_f_add1.inputs[0])
        links.new(math_sin_n.outputs[0], math_f_div.inputs[0])
        links.new(math_f_add1.outputs[0], math_f_div.inputs[1])
        links.new(g_in.outputs['Radius'], math_strand_r.inputs[0])
        links.new(math_f_div.outputs[0], math_strand_r.inputs[1])
        links.new(g_in.outputs['Radius'], math_ring_r.inputs[0])
        links.new(math_strand_r.outputs[0], math_ring_r.inputs[1])
        links.new(strand_idx.outputs[0], math_idx_fac.inputs[0])
        links.new(g_in.outputs['Strands'], math_idx_fac.inputs[1])
        links.new(math_idx_fac.outputs[0], math_base_angle.inputs[0])
        links.new(strand_idx.outputs[0], math_mod2.inputs[0])
        links.new(math_mod2.outputs[0], math_sign.inputs[0])
        links.new(math_sign.outputs[0], math_sign_final.inputs[0])
        links.new(g_in.outputs['Synthetic'], switch_sign.inputs[0])
        links.new(math_sign_final.outputs[0], switch_sign.inputs[2])
        links.new(g_in.outputs['Twist'], math_2pi.inputs[0])
        links.new(spline_param.outputs['Factor'], math_twist_sum.inputs[0])
        links.new(math_2pi.outputs[0], math_twist_sum.inputs[1])
        links.new(math_twist_sum.outputs[0], math_twist_angle.inputs[0])
        links.new(switch_sign.outputs[0], math_twist_angle.inputs[1])
        links.new(math_base_angle.outputs[0], math_total_angle.inputs[0])
        links.new(math_twist_angle.outputs[0], math_total_angle.inputs[1])
        links.new(math_total_angle.outputs[0], math_cos.inputs[0])
        links.new(math_total_angle.outputs[0], math_sin.inputs[0])
        links.new(strand_idx.outputs[0], math_weave_pi.inputs[0])
        links.new(spline_param.outputs['Factor'], math_weave_turns.inputs[0])
        links.new(math_weave_pi.outputs[0], math_weave_sum.outputs[0])
        links.new(math_weave_turns.outputs[0], math_weave_sum.inputs[1])
        links.new(math_weave_sum.outputs[0], math_weave_sin.inputs[0])
        links.new(math_weave_sin.outputs[0], math_weave_fac.inputs[0])
        links.new(math_weave_fac.outputs[0], math_weave_off.inputs[0])
        links.new(g_in.outputs['Radius'], math_weave_off.inputs[1])
        links.new(g_in.outputs['Synthetic'], switch_weave.inputs[0])
        links.new(math_weave_off.outputs[0], switch_weave.inputs[2])
        links.new(math_ring_r.outputs[0], math_final_r_off.inputs[0])
        links.new(switch_weave.outputs[0], math_final_r_off.inputs[1])
        links.new(curve_tangent.outputs[0], vec_binormal.inputs[0])
        links.new(curve_norm.outputs[0], vec_binormal.inputs[1])
        math_rcos = nodes.new('ShaderNodeMath'); math_rcos.operation = 'MULTIPLY'
        math_rsin = nodes.new('ShaderNodeMath'); math_rsin.operation = 'MULTIPLY'
        links.new(math_final_r_off.outputs[0], math_rcos.inputs[0]); links.new(math_cos.outputs[0], math_rcos.inputs[1])
        links.new(math_final_r_off.outputs[0], math_rsin.inputs[0]); links.new(math_sin.outputs[0], math_rsin.inputs[1])
        links.new(math_rcos.outputs[0], vec_norm_off.inputs[0])
        links.new(curve_norm.outputs[0], vec_norm_off.inputs[1])
        links.new(math_rsin.outputs[0], vec_binorm_off.inputs[0])
        links.new(vec_binormal.outputs[0], vec_binorm_off.inputs[1])
        links.new(vec_norm_off.outputs[0], vec_total_off.inputs[0])
        links.new(vec_binorm_off.outputs[0], vec_total_off.inputs[1])
        links.new(dup_elements.outputs[0], set_pos.inputs[0])
        links.new(vec_total_off.outputs[0], set_pos.inputs['Offset'])
        links.new(set_pos.outputs[0], curve_to_mesh.inputs['Curve'])
        links.new(prof_strand.outputs[0], curve_to_mesh.inputs['Profile Curve'])
        links.new(math_strand_r.outputs[0], prof_strand.inputs['Radius'])
        links.new(resample.outputs[0], curve_to_tube.inputs['Curve'])
        links.new(prof_tube.outputs[0], curve_to_tube.inputs['Profile Curve'])
        links.new(g_in.outputs['Radius'], prof_tube.inputs['Radius'])
        links.new(g_in.outputs['Tube Mode'], switch_mode.inputs[0])
        links.new(curve_to_mesh.outputs['Mesh'], switch_mode.inputs[1])
        links.new(curve_to_tube.outputs['Mesh'], switch_mode.inputs[2])
        links.new(switch_mode.outputs[0], set_mat.inputs['Geometry'])
        links.new(set_mat.outputs['Geometry'], g_out.inputs['Geometry'])

    # Retrieve sockets for drivers (must be outside the 'if not gn_group' block)
    iface = gn_group.interface
    rad_sock = iface.items_tree.get("Radius")
    strands_sock = iface.items_tree.get("Strands")
    twist_sock = iface.items_tree.get("Twist")
    tube_sock = iface.items_tree.get("Tube Mode")
    synth_sock = iface.items_tree.get("Synthetic")

    mod = rope_obj.modifiers.new(name=f"{MOD_PREFIX}Native_Rope", type='NODES')
    mod.node_group = gn_group
    
    # Drivers
    if rad_sock: create_driver(rope_obj, '["rope_radius"]', mod.name, rad_sock.identifier)
    if strands_sock: create_driver(rope_obj, '["rope_strands"]', mod.name, strands_sock.identifier)
    if twist_sock: create_driver(rope_obj, '["rope_twist"]', mod.name, twist_sock.identifier)
    if tube_sock: create_driver(rope_obj, '["rope_tube_mode"]', mod.name, tube_sock.identifier)
    if synth_sock: create_driver(rope_obj, '["rope_is_synthetic"]', mod.name, synth_sock.identifier)
    '''
    replace_function('core.py', 'setup_native_rope_gn', new_body)

