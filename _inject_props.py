# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import re

prop_file = 'properties.py'

new_props = '''
    # Literal Properties
    gear_radius: bpy.props.FloatProperty(name="Gear Radius", default=0.05, min=0.001, unit='LENGTH', update=update_radius_prop)
    gear_width: bpy.props.FloatProperty(name="Gear Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    gear_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=12, min=3, update=wrapper_regenerate)
    gear_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    rack_rack_width: bpy.props.FloatProperty(name="Rack Width", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rack_rack_height: bpy.props.FloatProperty(name="Rack Height", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rack_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=12, min=1, update=wrapper_regenerate)
    rack_tooth_depth: bpy.props.FloatProperty(name="Tooth Depth", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    fastener_radius: bpy.props.FloatProperty(name="Fastener Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    fastener_length: bpy.props.FloatProperty(name="Fastener Length", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    spring_radius: bpy.props.FloatProperty(name="Spring Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    spring_wire_thickness: bpy.props.FloatProperty(name="Wire Thickness", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    spring_turns: bpy.props.IntProperty(name="Turns", default=12, min=1, update=wrapper_regenerate)
    
    chain_pitch: bpy.props.FloatProperty(name="Pitch", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_roller_radius: bpy.props.FloatProperty(name="Roller Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_roller_length: bpy.props.FloatProperty(name="Roller Length", default=0.015, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_plate_height: bpy.props.FloatProperty(name="Plate Height", default=0.01, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    chain_plate_thickness: bpy.props.FloatProperty(name="Plate Thickness", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    belt_width: bpy.props.FloatProperty(name="Belt Width", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    belt_thickness: bpy.props.FloatProperty(name="Belt Thickness", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)

    wheel_base_radius: bpy.props.FloatProperty(name="Wheel Base Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_base_width: bpy.props.FloatProperty(name="Wheel Base Width", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    wheel_tread_count: bpy.props.IntProperty(name="Tread Count", default=12, min=1, update=wrapper_regenerate)

    pulley_base_radius: bpy.props.FloatProperty(name="Base Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pulley_width: bpy.props.FloatProperty(name="Width", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pulley_groove_depth: bpy.props.FloatProperty(name="Groove Depth", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    pulley_teeth_count: bpy.props.IntProperty(name="Teeth Count", default=12, min=3, update=wrapper_regenerate)

    rope_radius: bpy.props.FloatProperty(name="Rope Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rope_length: bpy.props.FloatProperty(name="Rope Length", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    rope_strands: bpy.props.IntProperty(name="Strands", default=12, min=1, update=wrapper_regenerate)

    shape_size: bpy.props.FloatProperty(name="Size", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_length_x: bpy.props.FloatProperty(name="Length (X)", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_width_y: bpy.props.FloatProperty(name="Width (Y)", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_height_z: bpy.props.FloatProperty(name="Height (Z)", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_radius: bpy.props.FloatProperty(name="Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_height: bpy.props.FloatProperty(name="Height", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_vertices: bpy.props.IntProperty(name="Vertices", default=32, min=3, update=wrapper_regenerate)
    shape_segments: bpy.props.IntProperty(name="Segments", default=32, min=3, update=wrapper_regenerate)
    shape_subdivisions: bpy.props.IntProperty(name="Subdivisions", default=2, min=1, update=wrapper_regenerate)
    shape_major_radius: bpy.props.FloatProperty(name="Major Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_tube_radius: bpy.props.FloatProperty(name="Tube Radius", default=0.004, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    shape_horizontal_segments: bpy.props.IntProperty(name="Horizontal Segments", default=48, min=3, update=wrapper_regenerate)
    shape_vertical_segments: bpy.props.IntProperty(name="Vertical Segments", default=12, min=3, update=wrapper_regenerate)

    elec_case_length: bpy.props.FloatProperty(name="Case Length", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    elec_half_width: bpy.props.FloatProperty(name="Half Width", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    elec_case_height: bpy.props.FloatProperty(name="Case Height", default=0.02, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    elec_radius: bpy.props.FloatProperty(name="Radius", default=0.05, min=0.001, unit='LENGTH', update=wrapper_regenerate)
    elec_length: bpy.props.FloatProperty(name="Length", default=0.1, min=0.001, unit='LENGTH', update=wrapper_regenerate)
'''

with open(prop_file, 'r', encoding='utf-8') as f:
    content = f.read()

if 'gear_radius: bpy.props.FloatProperty' not in content:
    insert_pos = content.find('outer_radius: bpy.props.FloatProperty')
    if insert_pos != -1:
        content = content[:insert_pos] + new_props + '\n    ' + content[insert_pos:]
        with open(prop_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print('Injected literal properties.')
    else:
        print('Could not find insertion point.')
else:
    print('Properties already exist.')

