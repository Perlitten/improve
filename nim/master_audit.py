import os
import subprocess

GROUPS = {
    "Vision_and_Core": ["00", "01", "02"],
    "Engine_and_Data": ["05", "08", "09", "10"],
    "Security_and_Ops": ["07.1", "17", "22", "24", "25"],
    "UI_and_Clinical": ["19", "21", "23"]
}

def run_group_audit(group_name, prefixes):
    print(f"\n--- STARTING MASTER AUDIT: {group_name} ---")
    prefix_str = " ".join(prefixes)
    cmd = f"python -u d:\\Nvidia\\nim_orchestrator.py {prefix_str}"
    
    # We rename the task for each run
    # Note: nim_orchestrator uses prefixes as task name if we change it slightly
    # Let's modify nim_orchestrator to accept a task name optionally
    subprocess.run(f"python -u d:\\Nvidia\\nim_orchestrator.py --task \"Group Audit: {group_name}\" --prefixes {prefix_str}", shell=True)

if __name__ == "__main__":
    # First, let's make a small tweak to nim_orchestrator to accept --task and --prefixes
    # Actually, I'll just run it as is, but it's better to update it.
    pass
