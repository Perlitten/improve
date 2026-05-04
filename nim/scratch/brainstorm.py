import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def brainstorm():
    # Using 70B for all roles to ensure stability and speed
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Architect Opening Proposal ---")
    proposal = model.invoke("Design a top-tier UX concept for the 'Soft Recovery App'. Theme: 'The Digital Sanctuary'. Focus on non-intrusive biometric visualization using the 'Aura' concept. Provide 3 specific UI patterns.").content
    print(proposal)

    print("\n--- [Council] Designer Critique & Refinement ---")
    critique = model.invoke(f"Critique this UX proposal from a high-end product design perspective (Apple/Airbnb style). Focus on 'Haptic Serenity', 'Glassmorphism', and premium typography (Inter/Outfit).\n\nProposal: {proposal}").content
    print(critique)

    print("\n--- [Council] Psychologist Safety Check ---")
    safety = model.invoke(f"Analyze this for 'No-Pressure Paradigm' and clinical safety. Ensure notifications are smart, metaphor-based, and personalized without causing anxiety. How should we handle 'negative' biometric shifts?\n\nDesign Context: {critique}").content
    print(safety)

if __name__ == "__main__":
    brainstorm()
