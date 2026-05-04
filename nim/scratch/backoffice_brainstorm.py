import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def brainstorm():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Architect: Backoffice Infrastructure ---")
    proposal = model.invoke("Design the architecture for the SRA Backoffice (Module 06). It must handle Shadow_UUIDs, GraphRAG visualization for admins, and a Notification Metaphor Registry. Focus on the 'Control Tower' metaphor.").content
    print(proposal)

    print("\n--- [Council] Designer: Backoffice UX/UI ---")
    critique = model.invoke(f"Design a 'top-tier' UI for this Backoffice. It should look like a mission control room—high information density but calm. Dark mode, cyan/amber accents, data-dense maps. How do we visualize 'Aura Drift' for thousands of users simultaneously?\n\nProposal: {proposal}").content
    print(critique)

    print("\n--- [Council] Operations/Security: Safety First ---")
    safety = model.invoke(f"How do we ensure the Backoffice is PII-firewalled? How do admins interact with PJKG without seeing PHI? Suggest a 'Blind Triage' workflow.\n\nContext: {critique}").content
    print(safety)

if __name__ == "__main__":
    brainstorm()
