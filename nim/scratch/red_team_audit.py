import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def red_team():
    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")

    print("\n--- [Council] Skeptical Clinician: The 'Too Soft' Trap ---")
    clinician = model.invoke("Critique the 'No-Pressure Paradigm'. When does 'Soft' become 'Ineffective'? If a user is spiraling but the system only gives 'Metaphors', is that clinical negligence? Find the fail-point in our safety logic.").content
    print(clinician)

    print("\n--- [Council] Black-Hat Architect: Shadow_UUID Leakage ---")
    security = model.invoke(f"Find the hole in our PII isolation. We use Shadow_UUIDs, but where is the 'Identity Vault'? If an attacker gets DB access, how can they reverse-engineer the identity? Is the 'Masked Socket Proxy' a single point of failure?\n\nContext: {clinician}").content
    print(security)

    print("\n--- [Council] Performance Engineer: GraphRAG Latency & Scaling ---")
    scaling = model.invoke(f"Neo4j + LLM + Real-time Biometrics. What is the P99 latency? How do we handle millions of personalized subgraphs? Is the PJKG architecture actually implementable at scale, or is it a research project?\n\nContext: {security}").content
    print(scaling)

    print("\n--- [Council] Product Strategist: The Cold Start & Offline Void ---")
    product = model.invoke(f"What happens in a tunnel with no WiFi? What happens in Day 1 with no data? The system seems to rely on 'Big Data' history. How do we prevent a 'Dead Experience' for new or offline users?\n\nContext: {scaling}").content
    print(product)

if __name__ == "__main__":
    red_team()
