import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def run_file_based_council():
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    files.sort()
    
    file_manifest = "\n".join([f"- {f}" for f in files])
    
    full_context = f"FILE MANIFEST (Verified existing files):\n{file_manifest}\n\n"
    for f in files:
        with open(os.path.join(vault_path, f), 'r', encoding='utf-8') as file:
            full_context += f"\n\n--- FILE: {f} ---\n{file.read()}\n"

    roles = {
        "SECURITY_ARCHITECT": "Focus on data protection, encryption (AES/KMS), and anonymity breaches.",
        "CLINICAL_LEAD": "Focus on suicide prevention protocols, metaphor triggers, and duty of care.",
        "UX_MOBILE_LEAD": "Focus on Android implementation, battery impact, and DCI accuracy.",
        "PRODUCT_FINOPS": "Focus on monetization, backoffice ops, and localization."
    }

    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
    output_dir = r"d:\Nvidia\scratch\council_results"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Council starting Sequential Audit of {len(files)} files. Manifest verified.\n")

    for role_name, role_desc in roles.items():
        print(f"--- Calling {role_name} ---")
        prompt = f"""
        You are the {role_name}. {role_desc}
        Review the following SRA project docs. 
        
        Note: The file list below IS verified. If you claim a file is missing, double check the manifest.
        
        TASK:
        1. Find 2 CRITICAL architectural or clinical failures.
        2. Status: GO or NO-GO.
        3. Specific fixes required.
        
        DOCS (Top 60k chars):
        {full_context[:60000]}
        """
        verdict = model.invoke(prompt).content
        
        with open(os.path.join(output_dir, f"{role_name}.md"), "w", encoding='utf-8') as f_out:
            f_out.write(verdict)
        
        print(f"Verdict for {role_name} saved.")
        print(verdict[:500] + "...") # Print preview
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_file_based_council()
