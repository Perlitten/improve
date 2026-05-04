import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def run_sequential_council():
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    files.sort() # Ensure consistent order
    
    full_context = ""
    for f in files:
        with open(os.path.join(vault_path, f), 'r', encoding='utf-8') as file:
            content = file.read()
            full_context += f"\n\n--- FILE: {f} ---\n{content}\n"

    roles = {
        "SECURITY_ARCHITECT": "Review for Identity leaks, Sync collisions, and Anonymity breaches.",
        "CLINICAL_LEAD": "Review for Metaphor safety, Crisis hand-off legalities, and No-Pressure efficacy.",
        "UX_MOBILE_LEAD": "Review for DCI accuracy, Battery/Thermal issues, and Android-native feasibility.",
        "PRODUCT_FINOPS": "Review for Backoffice ROI, Token budgets, and Localization gaps."
    }

    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
    
    print(f"Council starting Sequential Audit of {len(files)} files...\n")

    for role_name, role_desc in roles.items():
        print(f"--- Calling {role_name} ---")
        prompt = f"""
        You are the {role_name}. {role_desc}
        Review the following SRA project docs.
        
        CRITICAL TASKS:
        1. Find EXACTLY 2 critical failures or contradictions in the current docs.
        2. Give a 'GO' or 'NO-GO' status.
        3. Identify any missing file that MUST exist for your department.
        
        DOCS CONTEXT (Top 60k chars):
        {full_context[:60000]}
        """
        verdict = model.invoke(prompt).content
        print(verdict)
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_sequential_council()
