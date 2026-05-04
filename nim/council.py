import os
import requests
import argparse
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# Configuration
NIM_URL = "https://integrate.api.nvidia.com/v1"
API_KEY = os.getenv("NVIDIA_API_KEY")
OBSIDIAN_URL = "http://127.0.0.1:27123"
OBSIDIAN_KEY = "9d59473739d28df112a36b4e30b9a193e4cfb76257498302b1bbd58d25cb72dc"

# The Council Members
COUNCIL = {
    "Architect": "meta/llama-3.1-405b-instruct",
    "Security": "meta/llama-3.1-70b-instruct",
    "Coder": "mistralai/mistral-large-2-instruct"
}

def get_all_notes():
    headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}"}
    try:
        # Note: Local REST API list folder needs a trailing slash
        response = requests.get(f"{OBSIDIAN_URL}/vault/Memory/projects/soft-recovery-app/", headers=headers, timeout=5)
        if response.status_code == 200:
            return [f["name"] for f in response.json() if not f.get("isDir")]
        else:
            print(f"Error listing files: {response.status_code}")
            return []
    except Exception as e:
        print(f"Exception during list: {e}")
        return []

def fetch_note_by_prefix(prefix, notes):
    for note in notes:
        if note.startswith(f"{prefix} "):
            headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}"}
            try:
                response = requests.get(f"{OBSIDIAN_URL}/vault/Memory/projects/soft-recovery-app/{note}", headers=headers, timeout=5)
                return note, response.text
            except:
                return None, None
    return None, None

def ask_member(role, model, prompt, context):
    client = OpenAI(base_url=NIM_URL, api_key=API_KEY)
    system_msg = f"You are the {role} of the Soft Recovery App. Analyze the context and provide a brief, high-impact critique."
    print(f"[Council] {role} ({model}) is starting analysis...")
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Context:\n{context}\n\nTask: {prompt}"}
            ],
            temperature=0.1
        )
        print(f"[Council] {role} finished.")
        return f"### {role} ({model})\n{completion.choices[0].message.content}\n"
    except Exception as e:
        print(f"[Council] {role} ERROR: {e}")
        return f"### {role} ERROR: {e}\n"

def main():
    parser = argparse.ArgumentParser(description="SRA AI Council of Models")
    parser.add_argument("--task", required=True, help="What to review?")
    parser.add_argument("--files", required=True, help="Comma-separated prefixes (e.g. 07.1, 19)")
    args = parser.parse_args()

    # Load context
    print("--- Connecting to Obsidian ---")
    notes = get_all_notes()
    if not notes:
        print("Error: Could not list notes in Obsidian.")
        return

    context = ""
    for prefix in args.files.split(","):
        name, content = fetch_note_by_prefix(prefix.strip(), notes)
        if content: 
            context += f"\n\n--- {name} ---\n{content}"
            print(f"Loaded Context: {name}")

    if not context:
        print("Error: No context files found matching prefixes.")
        return

    print(f"--- Convening the Council: {args.task} ---")
    
    results = []
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(ask_member, role, model, args.task, context) for role, model in COUNCIL.items()]
        for future in futures:
            results.append(future.result())

    # Summary by Architect
    print("[Council] Lead Architect is summarizing...")
    architect_model = COUNCIL["Architect"]
    client = OpenAI(base_url=NIM_URL, api_key=API_KEY)
    
    try:
        final_completion = client.chat.completions.create(
            model=architect_model,
            messages=[
                {"role": "system", "content": "You are the Lead Architect. Summarize the council's findings and give Action Items."},
                {"role": "user", "content": "\n".join(results)}
            ]
        )
        
        full_report = f"# Council Report: {args.task}\n\n" + "\n".join(results) + "\n## FINAL CONSENSUS\n" + final_completion.choices[0].message.content
        
        # Save to Obsidian
        report_name = f"27 - Council Report - {args.task.replace(' ', '_')}.md"
        report_path = f"Memory/projects/soft-recovery-app/{report_name}"
        headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}", "Content-Type": "text/markdown"}
        requests.put(f"{OBSIDIAN_URL}/vault/{report_path}", headers=headers, data=full_report.encode('utf-8'), timeout=10)
        
        print(f"Council finished! Report saved as: {report_name}")
    except Exception as e:
        print(f"Final summary error: {e}")

if __name__ == "__main__":
    main()
