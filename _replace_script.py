# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T (GPL COMPLIANT)
# This add-on is protected under the GNU General Public License (GPL) to ensure 
# fair use and free distribution. The original architecture, source code, and 
# design logic are the intellectual property of Greenlex Systems Services Incorporated. 
#
# No party is authorized to claim authorship or ownership of this original work.
# --------------------------------------------------------------------------------



import os
import re

ui_file = 'panels/ui_parts.py'
prop_file = 'properties.py'

print("Patching ui_parts.py")
try:
    with open(ui_file, 'r', encoding='utf-8') as f:
        ui_text = f.read()

    ui_text = ui_text.replace('base_box.prop(props, "radius")', 'base_box.prop(props, "wheel_base_radius")')
    ui_text = ui_text.replace('base_box.prop(props, "length", text="Width")', 'base_box.prop(props, "wheel_base_width")')
    ui_text = ui_text.replace('tread_box.prop(props, "teeth", text="Line Count")', 'tread_box.prop(props, "wheel_tread_count")')
    ui_text = ui_text.replace('sub_box.prop(props, "teeth", text="Count")', 'sub_box.prop(props, "wheel_tread_count")')

    ui_text = ui_text.replace('edit_box.prop(props, "radius", text="Base Radius")', 'edit_box.prop(props, "pulley_base_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "length", text="Width")', 'edit_box.prop(props, "pulley_width")')
    ui_text = ui_text.replace('edit_box.prop(props, "tooth_depth", text="Groove Depth")', 'edit_box.prop(props, "pulley_groove_depth")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Teeth Count")', 'edit_box.prop(props, "pulley_teeth_count")')

    ui_text = ui_text.replace('edit_box.prop(props, "radius", text="Radius")', 'edit_box.prop(props, "rope_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "length")', 'edit_box.prop(props, "rope_length")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Strands")', 'edit_box.prop(props, "rope_strands")')

    ui_text = ui_text.replace('edit_box.prop(props, "length", text="Size")', 'edit_box.prop(props, "shape_size")')
    ui_text = ui_text.replace('edit_box.prop(props, "length", text="Length (X)")', 'edit_box.prop(props, "shape_length_x")')
    ui_text = ui_text.replace('edit_box.prop(props, "radius", text="Width (Y)")', 'edit_box.prop(props, "shape_width_y")')
    ui_text = ui_text.replace('edit_box.prop(props, "height", text="Height (Z)")', 'edit_box.prop(props, "shape_height_z")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Vertices")', 'edit_box.prop(props, "shape_vertices")')
    ui_text = ui_text.replace('edit_box.prop(props, "length", text="Height")', 'edit_box.prop(props, "shape_height")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Segments")', 'edit_box.prop(props, "shape_segments")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Subdivisions")', 'edit_box.prop(props, "shape_subdivisions")')
    ui_text = ui_text.replace('edit_box.prop(props, "radius", text="Major Radius")', 'edit_box.prop(props, "shape_major_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "tooth_depth", text="Tube Radius")', 'edit_box.prop(props, "shape_tube_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth", text="Horizontal Segments")', 'edit_box.prop(props, "shape_horizontal_segments")')
    ui_text = ui_text.replace('edit_box.prop(props, "teeth_minor", text="Vertical Segments")', 'edit_box.prop(props, "shape_vertical_segments")')

    ui_text = ui_text.replace('edit_box.prop(props, "radius", text="Motor Radius")', 'edit_box.prop(props, "motor_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "length", text="Motor Length")', 'edit_box.prop(props, "motor_length")')
    ui_text = ui_text.replace('edit_box.prop(props, "joint_pin_radius", text="Shaft Radius")', 'edit_box.prop(props, "shaft_radius")')
    ui_text = ui_text.replace('edit_box.prop(props, "joint_pin_length", text="Shaft Length")', 'edit_box.prop(props, "shaft_length")')

    with open(ui_file, 'w', encoding='utf-8') as f:
        f.write(ui_text)
    print("ui_parts.py patched.")
except Exception as e:
    print("Error patching ui_parts.py:", e)

print("Patching properties.py")
try:
    with open(prop_file, 'r', encoding='utf-8') as f:
        prop_text = f.read()

    def replace_in_func(func_name, replacements):
        global prop_text
        start = prop_text.find(f'def {func_name}(')
        if start == -1: return
        end = prop_text.find('\\ndef ', start + 10)
        if end == -1: end = len(prop_text)
        
        func_body = prop_text[start:end]
        for old, new in replacements.items():
            func_body = func_body.replace(old, new)
        prop_text = prop_text[:start] + func_body + prop_text[end:]

    replace_in_func('generate_chain_link_mesh', {
        'props.length': 'props.chain_pitch',
        'props.radius': 'props.chain_roller_radius',
        'props.roller_length': 'props.chain_roller_length',
        'props.tooth_depth': 'props.chain_plate_thickness',
        'props.tooth_width': 'props.chain_plate_height'
    })

    start_belt = prop_text.find("if props.type_chain == 'BELT':")
    if start_belt != -1:
        end_belt = prop_text.find("# --- AI Editor Note:", start_belt)
        if end_belt != -1:
            func_body = prop_text[start_belt:end_belt]
            func_body = func_body.replace('props.chain_roller_radius', 'props.belt_width')
            func_body = func_body.replace('props.chain_pitch', 'props.chain_pitch')
            func_body = func_body.replace('props.chain_plate_thickness', 'props.belt_thickness')
            prop_text = prop_text[:start_belt] + func_body + prop_text[end_belt:]

    replace_in_func('_generate_rack_gear_mesh', {
        'props.teeth': 'props.rack_teeth_count',
        'props.length': 'props.rack_length',
        'props.radius': 'props.rack_rack_width',
        'props.height': 'props.rack_rack_height',
        'props.tooth_depth': 'props.rack_tooth_depth'
    })

    replace_in_func('_generate_circular_gear_mesh', {
        'props.teeth': 'props.gear_teeth_count',
        'props.radius': 'props.gear_radius',
        'props.length': 'props.gear_width',
        'props.tooth_depth': 'props.gear_tooth_depth'
    })

    replace_in_func('generate_fastener_mesh', {
        'props.radius': 'props.fastener_radius',
        'props.length': 'props.fastener_length'
    })

    replace_in_func('generate_wheel_mesh', {
        'props.radius': 'props.wheel_base_radius',
        'props.length': 'props.wheel_base_width',
        'props.teeth': 'props.wheel_tread_count'
    })

    replace_in_func('generate_pulley_mesh', {
        'props.radius': 'props.pulley_base_radius',
        'props.length': 'props.pulley_width',
        'props.tooth_depth': 'props.pulley_groove_depth',
        'props.teeth': 'props.pulley_teeth_count'
    })

    replace_in_func('generate_rope_mesh', {
        'props.radius': 'props.rope_radius',
        'props.length': 'props.rope_length',
        'props.teeth': 'props.rope_strands',
        'props.tooth_depth': 'props.rope_radius * 0.9'
    })

    start_sh = prop_text.find('def generate_basic_shape_mesh')
    if start_sh != -1:
        end_sh = prop_text.find('\\ndef ', start_sh + 10)
        if end_sh == -1: end_sh = len(prop_text)
        func_body = prop_text[start_sh:end_sh]
        
        func_body = func_body.replace('props.length/2.0', 'props.shape_size/2.0', 1) 
        
        c_idx = func_body.find("'SHAPE_CUBE':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.length', 'props.shape_length_x')
            s = s.replace('props.radius', 'props.shape_width_y')
            s = s.replace('props.tooth_depth', 'props.shape_height_z')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_CIRCLE':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_radius')
            s = s.replace('props.teeth', 'props.shape_vertices')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_UVSPHERE':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_radius')
            s = s.replace('props.teeth', 'props.shape_segments')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_ICOSPHERE':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_radius')
            s = s.replace('props.teeth', 'props.shape_subdivisions')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_CYLINDER':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_radius')
            s = s.replace('props.teeth', 'props.shape_vertices')
            s = s.replace('props.length', 'props.shape_height')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_CONE':")
        if c_idx != -1:
            c_end = func_body.find("elif", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_radius')
            s = s.replace('props.teeth', 'props.shape_vertices')
            s = s.replace('props.length', 'props.shape_height')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        c_idx = func_body.find("'SHAPE_TORUS':")
        if c_idx != -1:
            c_end = func_body.find("def ", c_idx)
            if c_end == -1: c_end = len(func_body)
            s = func_body[c_idx:c_end]
            s = s.replace('props.radius', 'props.shape_major_radius')
            s = s.replace('props.tooth_depth', 'props.shape_tube_radius')
            s = s.replace('props.teeth_minor', 'props.shape_vertical_segments')
            s = s.replace('props.teeth', 'props.shape_horizontal_segments')
            func_body = func_body[:c_idx] + s + func_body[c_end:]

        prop_text = prop_text[:start_sh] + func_body + prop_text[end_sh:]

    replace_in_func('wrapper_regenerate', {
        'self.teeth': 'self.spring_turns',
        'self.radius': 'self.spring_radius',
        'self.tooth_depth': 'self.spring_wire_thickness'
    })

    with open(prop_file, 'w', encoding='utf-8') as f:
        f.write(prop_text)
    print("properties.py patched.")
except Exception as e:
    print("Error patching properties.py:", e)

