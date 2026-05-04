import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def behavior_council():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Psychologist: The 'Phone Greediness' Metric ---")
    psych = model.invoke("How can we use Screen Time and Unlock Frequency as a proxy for anxiety? Define the 'Digital Compulsion Index' (DCI). How do we distinguish 'Seeking Safety' (opening SRA) from 'Doomscrolling' (opening Social Media)?").content
    print(psych)

    print("\n--- [Council] Android Engineer: Privacy-First Usage Stats ---")
    android = model.invoke(f"How can we implement Screen Time tracking on Android (UsageStatsManager) while keeping it 'No-Pressure'? We need to know app-category time without seeing private data. How do we send this to the PJKG via gRPC?\n\nContext: {psych}").content
    print(android)

    print("\n--- [Council] Backoffice Architect: FinOps & Budgeting ---")
    finops = model.invoke("Define a 'Token Budgeting' system for the SRA Backoffice. How do we track the cost of LLM inference per user? How do we set alerts for 'Budget Drain' on users with low recovery progress? Suggest a dashboard layout for 'Recovery ROI'.").content
    print(finops)

if __name__ == "__main__":
    behavior_council()
