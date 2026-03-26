# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import os
import re

ops_list_file = 'ops_list.txt'
operators_file = 'operators.py'
ui_dir = 'panels'

with open(ops_list_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

replacements = {}
class_renames = {}
idname_renames = {}

for line in lines:
    line = line.strip()
    if not line:
        continue
    parts = line.split(' | ')
    if len(parts) == 3:
        old_class, old_idname, label = parts
        
        # Determine new names based strictly on literal label
        # Remove non-alphanumeric except spaces for processing
        clean_label = re.sub(r'[^a-zA-Z0-9\s/]', '', label)
        
        # New Class: Title case, remove spaces and slashes
        title_cased = ''.join(word.capitalize() for word in clean_label.replace('/', ' ').split())
        new_class = f'URDF_OT_{title_cased}'
        
        # New Idname: lowercase, spaces and slashes to underscores
        snake_cased = '_'.join(word.lower() for word in clean_label.replace('/', ' ').split())
        new_idname = f'urdf.{snake_cased}'
        
        # Only overwrite if it actually changed
        if old_class != new_class:
            class_renames[old_class] = new_class
        if old_idname != new_idname:
            idname_renames[old_idname] = new_idname

print(f"Total operator classes to rename: {len(class_renames)}")
print(f"Total operator idnames to rename: {len(idname_renames)}")

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changed = False
    
    for old_class, new_class in class_renames.items():
        if old_class in content:
            # Match whole words to avoid partial replacement bugs
            content = re.sub(r'\\b' + re.escape(old_class) + r'\\b', new_class, content)
            changed = True
            
    for old_idname, new_idname in idname_renames.items():
        if old_idname in content:
            content = re.sub(r'\\b' + re.escape(old_idname) + r'\\b', new_idname, content)
            changed = True
            
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched {filepath}")

# Files to patch
target_files = [operators_file, 'core.py', 'properties.py', '__init__.py']

if os.path.exists(ui_dir):
    for f in os.listdir(ui_dir):
        if f.endswith('.py'):
            target_files.append(os.path.join(ui_dir, f))

for f in target_files:
    if os.path.exists(f):
        replace_in_file(f)

