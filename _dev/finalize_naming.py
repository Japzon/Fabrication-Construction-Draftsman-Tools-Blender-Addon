import os
import re

def overhauled_file(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping: {filepath} (Not found)")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements based on project_management.txt Rules 15 & 16
    replacements = [
        (r'LSD_PT_Mechanical_Presets', 'LSD_PT_Mechanical_Presets'),
        (r'LSD_PT_Electronic_Presets', 'LSD_PT_Electronic_Presets'),
        (r'LSD_PT_Parametric_Toolkit', 'LSD_PT_Parametric_Toolkit'),
        (r'LSD_PT_Materials_And_Textures', 'LSD_PT_Materials_And_Textures'),
        (r'LSD_PT_Lighting_And_Atmosphere', 'LSD_PT_Lighting_And_Atmosphere'),
        (r'LSD_PT_Dimensions_And_Measuring', 'LSD_PT_Dimensions_And_Measuring'),
        (r'LSD_PT_Architectural_Presets', 'LSD_PT_Architectural_Presets'),
        (r'LSD_PT_Vehicle_Presets', 'LSD_PT_Vehicle_Presets'),
        (r'LSD_PT_Physics_Inertial', 'LSD_PT_Physics_Inertial'),
        (r'LSD_PT_Physics_Collision', 'LSD_PT_Physics_Collision'),
        (r'LSD_PT_Kinematics_Setup', 'LSD_PT_Kinematics_Setup'),
        (r'LSD_PT_Asset_Library_System', 'LSD_PT_Asset_Library_System'),
        (r'LSD_PT_Import_Export_System', 'LSD_PT_Import_Export_System'),
        (r'LSD_PT_Generate', 'LSD_PT_Generate'), 
        
        # Operators
        (r'LSD_OT_Open_Asset_Browser', 'LSD_OT_Open_Asset_Browser'),
        (r'LSD_OT_Add_Asset_Library', 'LSD_OT_Add_Asset_Library'),
        (r'LSD_OT_Register_Asset_Catalog', 'LSD_OT_Register_Asset_Catalog'),
        (r'LSD_OT_Mark_And_Upload_Asset', 'LSD_OT_Mark_And_Upload_Asset'),
        (r'LSD_OT_Generate_Robot_With_AI', 'LSD_OT_Generate_Robot_With_AI'),
        (r'LSD_OT_Setup_Example_Rover', 'LSD_OT_Setup_Example_Rover'),
        (r'LSD_OT_Setup_Example_Arm', 'LSD_OT_Setup_Example_Arm'),
        (r'LSD_OT_Setup_Mobile_Base', 'LSD_OT_Setup_Mobile_Base'),
        (r'LSD_OT_Setup_Quadruped', 'LSD_OT_Setup_Quadruped'),
        (r'LSD_OT_Clear_Physics', 'LSD_OT_Clear_Physics'),
        (r'LSD_OT_Rig_Parametric_Joint', 'LSD_OT_Rig_Parametric_Joint'),
        (r'LSD_OT_Create_Parametric_Chain', 'LSD_OT_Create_Parametric_Chain'),
        (r'LSD_OT_Add_Dimension', 'LSD_OT_Add_Dimension'),
        (r'LSD_OT_Remove_Dimension', 'LSD_OT_Remove_Dimension'),
        (r'LSD_OT_Apply_Material_Preset', 'LSD_OT_Apply_Material_Preset'),
        (r'LSD_OT_Reset_Part_Scale', 'LSD_OT_Reset_Part_Scale'),
        (r'LSD_OT_Spawn_Parametric_Part', 'LSD_OT_Spawn_Parametric_Part'),
    ]

    new_content = content
    for old, new in replacements:
        new_content = re.sub(old, new, new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Update: {filepath}")

def main():
    base_dir = r"c:\Users\japzo\OneDrive\Desktop\Blender Add-on Workshop\Fabrication-Construction-Draftsman-Tools-Automated"
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                overhauled_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
