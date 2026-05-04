import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def final_exhaustive_audit():
    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
    
    # Corrected absolute path
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    
    print(f"Auditing {len(files)} files in {vault_path}...")

    # We provide a detailed list of files to help the AI understand the scope
    file_list = "\n".join(files)

    prompt = f"""
    You are the Lead Red Team Architect for SRA (Soft Recovery Agency). 
    Project Scope: {file_list}
    
    We have covered Biometrics, GraphRAG, Localization, and Security.
    But we need to find the 'hidden' failures. 
    
    Specific audit targets:
    1. DEVICE OVERLOAD: How do we handle 24/7 DCI tracking on budget Android phones without killing the battery?
    2. DATA COLLISIONS: How do we sync a Graph (Neo4j) between 2 devices for the same user without a unique 'Master' ID (since we are anonymous)?
    3. LEGAL LIABILITY: If a user self-harms, can SRA be sued? Do we have a 'Crisis Hand-off' that is legally defensible?
    4. SUPPORT LOOPHOLE: How does an anonymous user open a support ticket for a billing issue without revealing their identity?
    5. THE 'METAPHOR MISFIRE': Can the AI generate a metaphor that is culturally insensitive or clinically dangerous?
    6. STORAGE BLOAT: What happens when the local PJKG graph on the phone hits 2GB?
    
    Look at the existing file list and identify what is MISSING or WEAK.
    Be BRUTAL.
    """
    
    audit_result = model.invoke(prompt).content
    print("\n--- [Council] RED TEAM FINAL VERDICT ---")
    print(audit_result)

if __name__ == "__main__":
    final_exhaustive_audit()
