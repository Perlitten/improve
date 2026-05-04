import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def run_fast_final_audit():
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    files.sort()
    
    # Selecting core files first to ensure they fit in 40k chars
    core_files = [
        "00 - Index.md", "19 - Clinical Safety & Crisis Protocols.md", 
        "20 - AI Governance and Evaluation.md", "44 - Data Protection and PHI Encryption.md",
        "07.1 - Security & Privacy Protocol.md", "38 - Architecture Stress Test and Mitigations.md"
    ]
    
    full_context = ""
    for f in core_files + [f for f in files if f not in core_files]:
        if len(full_context) > 40000: break
        with open(os.path.join(vault_path, f), 'r', encoding='utf-8') as file:
            full_context += f"\n\n--- FILE: {f} ---\n{file.read()}\n"

    roles = {
        "SECURITY_ARCHITECT": "Focus on Encryption, Redline Flow, and Anonymity.",
        "CLINICAL_LEAD": "Focus on Crisis safety and Multi-model consensus."
    }

    # Using 70B for speed and stability
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")
    
    print(f"Fast Final Council Audit starting...\n")

    for role_name, role_desc in roles.items():
        print(f"--- Calling {role_name} ---")
        prompt = f"""
        You are the {role_name}. {role_desc}
        Review the following SRA project docs.
        
        CRITICAL TASK:
        We have added 'Redline Escalation', 'Triple-Consensus Safety', and 'AES/KMS PHI Encryption'.
        Does this resolve the previous NO-GO?
        
        Status: GO or NO-GO.
        Reason: 
        
        DOCS:
        {full_context}
        """
        verdict = model.invoke(prompt).content
        print(verdict)
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_fast_final_audit()
