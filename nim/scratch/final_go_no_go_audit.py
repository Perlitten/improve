import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def run_final_go_no_go():
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    files.sort()
    
    full_context = ""
    for f in files:
        with open(os.path.join(vault_path, f), 'r', encoding='utf-8') as file:
            full_context += f"\n\n--- FILE: {f} ---\n{file.read()}\n"

    roles = {
        "SECURITY_ARCHITECT": "Focus on PHI Protection, Redline Escalation technicals, and AES/KMS.",
        "CLINICAL_LEAD": "Focus on Redline safety, Multi-model consensus, and Duty of Care."
    }

    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
    
    print(f"Final Council Audit starting...\n")

    for role_name, role_desc in roles.items():
        print(f"--- Calling {role_name} ---")
        prompt = f"""
        You are the {role_name}. {role_desc}
        Review the following SRA project docs.
        
        CRITICAL TASK:
        We have just implemented 'Redline Escalation', 'Triple-Consensus Safety', and 'AES/KMS PHI Encryption'.
        Does this resolve your previous NO-GO?
        
        Give a definitive 'GO' or 'NO-GO'.
        
        DOCS (Top 100k chars):
        {full_context[:100000]}
        """
        verdict = model.invoke(prompt).content
        print(verdict)
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_final_go_no_go()
