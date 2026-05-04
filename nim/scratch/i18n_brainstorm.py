import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def brainstorm():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Architect: Data-Driven L10n Strategy ---")
    proposal = model.invoke("Design a localization strategy for SRA. No hardcoded strings. How do we store Metaphor Templates for different languages (English, Russian, etc.)? Suggest a JSON schema for 'LocalizedMetaphor' nodes in the PJKG.").content
    print(proposal)

    print("\n--- [Council] Designer: Cultural UI Adaptability ---")
    critique = model.invoke(f"Critique the UI for international use. Do colors like 'Rose' for tension work everywhere? How do we adapt the 'Digital Sanctuary' for different cultural aesthetics?\n\nContext: {proposal}").content
    print(critique)

    print("\n--- [Council] Psychologist: Cultural Resonance of Metaphors ---")
    safety = model.invoke(f"How do metaphors change across cultures? A 'sea tide' might be scary for someone in a flood-prone region. How should the 'Localization Engine' handle emotional resonance?\n\nContext: {critique}").content
    print(safety)

if __name__ == "__main__":
    brainstorm()
