import os
import subprocess
import sys
import shutil
import re
from datetime import datetime
# Ensure current directory is in path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from zip_addon import zip_addon

ADDON_NAME = "fabrication_construction_draftsman_tools_automated"
OLD_ADDON_NAME = "automated_robot_cnc_dev_kit"
BLENDER_DEFAULT_PATH = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"

def find_blender():
    # Priority 1: Default path
    if os.path.exists(BLENDER_DEFAULT_PATH):
        return BLENDER_DEFAULT_PATH
    
    # Priority 2: Any Blender in Program Files (find the newest)
    base_dir = r"C:\Program Files\Blender Foundation"
    if os.path.exists(base_dir):
        folders = [f for f in os.listdir(base_dir) if f.startswith("Blender")]
        if folders:
            # Sort by version number (naive but works for 4.x)
            folders.sort(reverse=True)
            for folder in folders:
                exe = os.path.join(base_dir, folder, "blender.exe")
                if os.path.exists(exe):
                    return exe
    
    # Priority 3: System PATH
    try:
        result = subprocess.run(["where", "blender"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except:
        pass
        
    return None

def get_blender_version(path):
    # Try to extract version number from path (e.g. "4.5" from "Blender 4.5")
    match = re.search(r"Blender (\d+\.\d+)", path, re.I)
    if match:
        return match.group(1)
    return "4.5" # Fallback

def setup_dev():
    print("\n" + "="*50)
    print("  BLENDER DEVELOPMENT SETUP")
    print("="*50)
    
    blender_exe = find_blender()
    if not blender_exe:
        print("\n[ERROR] BLENDER EXECUTABLE NOT FOUND!")
        print("Please ensure Blender is installed in 'C:\\Program Files\\Blender Foundation'")
        return False
    
    version = get_blender_version(blender_exe)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("\n[ERROR] APPDATA environment variable not found!")
        return False
        
    addons_dir = os.path.join(appdata, "Blender Foundation", "Blender", version, "scripts", "addons")
    target_dir = os.path.join(addons_dir, ADDON_NAME)
    
    # Path cleaning for Windows shell
    source_dir = os.path.dirname(os.path.abspath(__file__)).rstrip('\\')
    target_dir = target_dir.rstrip('\\')
    
    print(f"\n[INFO] Blender Path:  {blender_exe}")
    print(f"[INFO] Project Path:  {source_dir}")
    print(f"[INFO] AppData Path:  {target_dir}")
    
    # Check if Blender is running (can block cleanup)
    try:
        tasklist = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq blender.exe'], capture_output=True, text=True).stdout
        if "blender.exe" in tasklist.lower():
            print("\n[WARNING] Blender is currently running!")
            print("Please close Blender to ensure the add-on update works correctly.")
            print("Attempting to continue anyway...")
    except:
        pass

    try:
        # Create AppData tree if missing
        if not os.path.exists(addons_dir):
            print(f"[INFO] Creating addons directory...")
            os.makedirs(addons_dir, exist_ok=True)
            
        # Robust Cleanup
        if os.path.exists(target_dir) or os.path.islink(target_dir):
            print(f"[INFO] Cleaning old add-on files...")
            # Attempt multiple ways to remove it
            subprocess.run(f'cmd /c "rmdir /S /Q \"{target_dir}\""', shell=True, capture_output=True)
            if os.path.exists(target_dir):
                # If still exists, try deleting it as a file (in case it's a broken symlink)
                try:
                    if os.path.islink(target_dir):
                        os.unlink(target_dir)
                    else:
                        shutil.rmtree(target_dir, ignore_errors=True)
                except:
                    pass
        
        # Double check cleanup
        if os.path.exists(target_dir):
            print(f"\n[ERROR] FAILED TO CLEANUP TARGET DIRECTORY!")
            print("Reason: Folder is likely locked by Blender or another program.")
            print(">>> FIX: Close Blender and try again.")
            return False

        # Attempt to Link (Works best for development)
        print(f"[INFO] Connecting project to Blender...")
        link_cmd = f'mklink /J "{target_dir}" "{source_dir}"'
        result = subprocess.run(link_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("[SUCCESS] Link created successfully!")
        else:
            # Fallback to Copying (Mirrors the folder without needing Admin)
            print("[INFO] Link failed (Admin might be required). Falling back to Sync...")
            # robocopy /MIR is fast and handles identical files efficiently
            sync_cmd = f'robocopy "{source_dir}" "{target_dir}" /MIR /XF *.zip *.pyc /XD __pycache__ .git .gemini'
            # robocopy exit codes 0-3 are considered success/no-error
            sync_result = subprocess.run(sync_cmd, shell=True, capture_output=True)
            
            if sync_result.returncode <= 3:
                print("[SUCCESS] Sync complete! (Note: Re-run this script after code changes)")
            else:
                print(f"\n[ERROR] FAILED TO SYNC FILES!")
                print(f"Details: {result.stderr.strip()}")
                return False
            
        # Rebuild Zip
        print(f"\n[INFO] Rebuilding Addon ZIP package...")
        zip_addon()
        print(f"[INFO] ZIP package rebuild complete.")
        
        # Launch Blender
        print(f"\n[SUCCESS] Attempting to launch Blender {version}...")
        py_cmd = f"import bpy; bpy.ops.preferences.addon_enable(module='{ADDON_NAME}')"
        
        # 0x00000008 is DETACHED_PROCESS
        # 0x00000010 is CREATE_NEW_CONSOLE
        # 0x04000000 is CREATE_NO_WINDOW
        DETACHED_PROCESS = 0x00000008
        
        try:
            # We use subprocess.Popen with DETACHED_PROCESS to ensure it outlives this script
            subprocess.Popen([blender_exe, "--python-expr", py_cmd], 
                             creationflags=DETACHED_PROCESS,
                             close_fds=True,
                             shell=False)
            
            print("\n[DONE] Blender launch command processed.")
            print("The terminal will now close automatically.")
            import time
            time.sleep(1.5) 
            return True
        except Exception as e:
            print(f"[ERROR] Launch failed: {e}")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        return False

def sync_git():
    print("\n" + "="*50)
    print("  GITHUB SYNC TOOL")
    print("="*50)
    
    # Ensure we are in the script's directory for git operations
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Check git
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except:
        print("\n[ERROR] GIT NOT FOUND!")
        return False
        
    # Re-initialize git if missing (e.g., after ZIP extraction)
    if not os.path.exists(".git"):
        print("[INFO] Repository not found. Initializing Git...")
        subprocess.run(["git", "init"], check=True)
        # We use the specific repository provided by the user
        repo_url = "https://github.com/Japzon/Fabrication-Construction-Draftsman-Tools-Automated.git"
        print(f"[INFO] Adding remote origin: {repo_url}")
        subprocess.run(["git", "remote", "add", "origin", repo_url], check=True)
        
    # Rebuild zip
    print("[INFO] Updating addon package...")
    zip_addon()
    
    # Git operations
    print("[INFO] Staging updates and removals...")
    subprocess.run(["git", "add", "-A"])
    
    # Any changes?
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        # Check if we still need to push/pull even if no local changes
        status = subprocess.run(["git", "status", "-sb"], capture_output=True, text=True).stdout
        if "behind" not in status and "ahead" not in status:
            print("\n[INFO] No changes detected. Repository is already up to date.")
            return True
        
    # Commit message (if changes exist)
    if diff.returncode != 0:
        print("\n" + "-"*30)
        msg = input("Enter commit message (Press Enter for auto-timestamp): ").strip()
        if not msg:
            msg = f"Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        print("-"*30)
        subprocess.run(["git", "commit", "-m", msg])

    # Sync with remote
    print("[INFO] Syncing with remote repository...")
    # Identify current branch
    branch_result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
    current_branch = branch_result.stdout.strip() or "main"
    
    print(f"[INFO] Pulling latest from origin/{current_branch}...")
    # Added --allow-unrelated-histories for cases where .git was re-initialized
    subprocess.run(["git", "pull", "--rebase", "--autostash", "--allow-unrelated-histories", "origin", current_branch])
    
    # Push
    print("\n[INFO] Pushing to GitHub...")
    result = subprocess.run(["git", "push", "origin", current_branch])
    
    if result.returncode == 0:
        print(f"\n[SUCCESS] Successfully pushed to {current_branch}!")
        return True
    else:
        # Fallback for common branch names if direct push fails
        if current_branch == "main":
            print("[INFO] Pushing to main failed, trying master...")
            result = subprocess.run(["git", "push", "origin", "master"])
        elif current_branch == "master":
            print("[INFO] Pushing to master failed, trying main...")
            result = subprocess.run(["git", "push", "origin", "main"])
            
    if result.returncode == 0:
        print("\n[SUCCESS] Successfully pushed to GitHub!")
        return True
    else:
        print("\n[ERROR] Push failed. Check your internet connection and git credentials.")
        print("Note: You may need to manually resolve merge conflicts if 'git pull' failed.")
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python dev_tool.py [start|push]")
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    if cmd == "start":
        if not setup_dev():
            print("\nSetup failed. Press Enter to see error...")
            input()
    elif cmd == "push":
        if not sync_git():
            print("\nSync failed. Press Enter to see error...")
            input()
        else:
            # Sync success usually needs a moment to see results before closing
            import time
            time.sleep(2)
    else:
        print(f"Unknown command: {cmd}")
