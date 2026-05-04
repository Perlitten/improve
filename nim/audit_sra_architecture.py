import os
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# NVIDIA NIM Config
MODEL = "meta/llama-3.1-405b-instruct"
NIM_CLIENT = OpenAI(
  base_url="https://integrate.api.nvidia.com/v1",
  api_key=os.getenv("NVIDIA_API_KEY")
)

# Obsidian API Config (from mcp_config)
OBSIDIAN_URL = "http://127.0.0.1:27123"
OBSIDIAN_KEY = "9d59473739d28df112a36b4e30b9a193e4cfb76257498302b1bbd58d25cb72dc"

CORE_FILES = [
    "Memory/projects/soft-recovery-app/00 - Index.md",
    "Memory/projects/soft-recovery-app/01 - Vision and Market Dynamics.md",
    "Memory/projects/soft-recovery-app/02 - Clinical Psychology and No-Pressure Paradigm.md",
    "Memory/projects/soft-recovery-app/05 - GraphRAG Core Engine.md",
    "Memory/projects/soft-recovery-app/07.1 - Security & Privacy Protocol.md",
    "Memory/projects/soft-recovery-app/19 - Clinical Safety & Crisis Protocols.md",
    "Memory/projects/soft-recovery-app/24 - AI Governance and Anti-Degradation Protocol.md"
]

def fetch_obsidian_note(path):
    headers = {"Authorization": f"Bearer {OBSIDIAN_KEY}"}
    try:
        # Note: Local REST API needs the path URL-encoded
        response = requests.get(f"{OBSIDIAN_URL}/vault/{path}", headers=headers)
        if response.status_code == 200:
            return response.text
        else:
            print(f"Warning: Could not fetch {path} (Status {response.status_code})")
            return None
    except Exception as e:
        print(f"Error fetching from Obsidian: {e}")
        return None

def save_obsidian_note(path, content):
    headers = {
        "Authorization": f"Bearer {OBSIDIAN_KEY}",
        "Content-Type": "text/markdown"
    }
    try:
        response = requests.put(f"{OBSIDIAN_URL}/vault/{path}", headers=headers, data=content.encode('utf-8'))
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"Error saving to Obsidian: {e}")
        return False

def run_peer_review():
    print("--- Fetching documentation from Obsidian via API ---")
    docs_content = ""
    for path in CORE_FILES:
        content = fetch_obsidian_note(path)
        if content:
            filename = path.split('/')[-1]
            docs_content += f"\n\n--- FILE: {filename} ---\n\n{content}"

    if not docs_content:
        print("Error: No documentation content retrieved.")
        return

    system_prompt = (
        "You are a Senior Systems Architect and Clinical Safety Officer. "
        "Review the following 'Soft Recovery App' (SRA) architecture for a mental health application. "
        "Your goal is to find critical flaws, 'Red Team' the security, and identify clinical risks. "
        "Provide a structured critique focusing on: \n"
        "1. PII/PHI leakage risks in the GraphRAG pipeline.\n"
        "2. Clinical safety of AI-driven 'Soft' insights.\n"
        "3. Scalability of the Neo4j-based PJKG.\n"
        "4. Practicality of the AI-Anti-Degradation protocol."
    )

    print(f"--- Calling NVIDIA NIM ({MODEL}) for Peer Review ---")
    
    try:
        completion = NIM_CLIENT.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the documentation:\n{docs_content}"}
            ],
            temperature=0.2,
            max_tokens=4000
        )
        
        report_content = completion.choices[0].message.content
        report_path = "Memory/projects/soft-recovery-app/26 - Peer Review Report (NVIDIA NIM).md"
        
        full_report = f"# 26 - Peer Review Report (NVIDIA NIM)\n\n**Model**: {MODEL}\n\n{report_content}"
        
        if save_obsidian_note(report_path, full_report):
            print(f"Audit complete! Report saved to Obsidian: {report_path}")
        else:
            print("Audit complete, but failed to save to Obsidian. Printing to console:")
            print(full_report)
            
    except Exception as e:
        print(f"Error during audit: {e}")

if __name__ == "__main__":
    run_peer_review()
