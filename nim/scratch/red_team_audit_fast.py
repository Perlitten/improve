import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def red_team():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Skeptical Clinician: The 'Too Soft' Trap ---")
    clinician = model.invoke("Critique the 'No-Pressure Paradigm'. Find the exact clinical fail-point. When does 'Soft' become negligence? Suggest a 'Hard Override' trigger.").content
    print(clinician)

    print("\n--- [Council] Black-Hat Architect: Shadow_UUID & Vault Privacy ---")
    security = model.invoke(f"Find the hole in Shadow_UUID. If we store the mapping in a central 'Identity Vault', isn't that vault a 'honeypot'? How do we prevent internal admins from de-anonymizing users? Suggest a 'Split-Key' or 'ZKP' approach.\n\nContext: {clinician}").content
    print(security)

    print("\n--- [Council] Performance Engineer: GraphRAG & Real-time Drift ---")
    scaling = model.invoke(f"Can Neo4j handle 1M+ active personalized subgraphs? What is the latency of a 'RAG-over-Graph' query for the 'Aura' visualization? Is this overkill? Suggest a 'Cached Aura' or 'Edge-inference' strategy.\n\nContext: {security}").content
    print(scaling)

    print("\n--- [Council] Product Strategist: Cold Start & Survival Mode ---")
    product = model.invoke(f"What is the experience for a user with NO data on Day 1? What if the user is offline for 48 hours? Does the 'Sanctuary' die? Suggest a 'Generic Archetype' and 'Local-First' strategy.\n\nContext: {scaling}").content
    print(product)

if __name__ == "__main__":
    red_team()
