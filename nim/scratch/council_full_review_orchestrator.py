import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

def run_council_audit():
    vault_path = r"D:\Obsidian\Memory\projects\soft-recovery-app"
    files = [f for f in os.listdir(vault_path) if f.endswith(".md")]
    
    # Load all content to give the Council full context
    full_context = ""
    for f in files:
        with open(os.path.join(vault_path, f), 'r', encoding='utf-8') as file:
            full_context += f"\n\n--- FILE: {f} ---\n" + file.read()

    roles = {
        "Security_Architect": "Focus on data leaks, anonymization bypass, and sync vulnerabilities.",
        "Clinical_Psychologist": "Focus on trigger safety, metaphor misuse, and clinical efficacy of the no-pressure model.",
        "Mobile_UX_Lead": "Focus on battery drain, haptic precision, and DCI tracking accuracy on Android.",
        "FinOps_Manager": "Focus on token burn, backoffice ROI, and localization gaps."
    }

    def get_role_verdict(role_name, role_desc):
        model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
        prompt = f"""
        You are the {role_name}. {role_desc}
        Review the entire SRA project documentation provided below.
        
        TASK:
        1. Find 3 CRITICAL contradictions or gaps.
        2. Give a 'GO' or 'NO-GO' for development start.
        3. Identify any file that is 'floating' (unlinked or outdated).
        
        CONTEXT:
        {full_context[:30000]} # Limiting context to stay within token bounds for the prompt
        """
        return f"\n=== {role_name} VERDICT ===\n" + model.invoke(prompt).content

    print(f"Council is reviewing {len(files)} files...")
    
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda r: get_role_verdict(r[0], r[1]), roles.items()))

    final_report = "\n".join(results)
    print(final_report)
    
    with open(r"d:\Nvidia\scratch\council_full_review.txt", "w", encoding='utf-8') as f:
        f.write(final_report)

if __name__ == "__main__":
    run_council_audit()
