# --------------------------------------------------------------------------------
# Copyright (c) 2026 Greenlex Systems Services Incorporated. All rights reserved.
#
# A C K N O W L E D G M E N T
# This work is not to be reproduced or used for developing monetized extensions 
# and applications except with a written agreement with Greenlex Systems Services Incorporated.
# --------------------------------------------------------------------------------


import os
import zipfile
import sys

def zip_addon():
    version_str = "latest"
    try:
        # Standard import if running via dev_tool or as module
        import config
        version_str = "-".join(map(str, config.ADDON_VERSION))
    except ImportError:
        # Fallback if config is not in path (rare but possible)
        pass
        
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    addon_folder_name = os.path.basename(addon_dir)
    
    # 1. Clean up old zip files to ensure repository stays thin
    print("[INFO] Cleaning up old .zip build artifacts...")
    for item in os.listdir(addon_dir):
        if item.endswith(".zip"):
            try:
                os.remove(os.path.join(addon_dir, item))
            except Exception as e:
                print(f"Warning: Could not remove old zip {item}: {e}")

    # The zip is saved inside the addon folder so it's tracked by git
    zip_name = f"Fabrication-Construction-Draftsman-Tools-Automated_v{version_str}.zip"
    zip_path = os.path.join(addon_dir, zip_name)
    
    print(f"Starting to zip addon folder with version {version_str}: {addon_folder_name}")
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(addon_dir):
                # Mandatory exclusions to keep the zip clean and small
                if any(x in root for x in ['__pycache__', '.git', '.gemini', '.idea', '.vscode']):
                    continue
                
                for file in files:
                    # Exclude the zip itself and the automation scripts
                    if file == zip_name or file.endswith('.zip'):
                        continue
                    if file == 'zip_addon.py' or file == 'patch_panels.py' or file == 'test_addon.py' or file == 'test_rna.py':
                        continue
                    if file.endswith('.bat') or file.endswith('.txt') or file.endswith('.md'):
                        # Optional: Keep logs and documentation out of the final install?
                        # For now, let's keep READMEs but skip logs.
                        if 'log' in file.lower() or 'Prompt' in file:
                            continue
                
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, addon_dir)
                    
                    # Use 'fabrication_construction_draftsman_tools_automated' as the root folder inside the zip
                    archive_path = os.path.join("fabrication_construction_draftsman_tools_automated", rel_path)
                    zipf.write(file_path, archive_path)
        
        print(f"Successfully zipped addon to: {zip_path}")
    except Exception as e:
        print(f"Error during zipping: {e}")

if __name__ == "__main__":
    zip_addon()

