import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from typing import TypedDict, List, Annotated, Dict
import operator

load_dotenv(r"d:\Nvidia\.env")

class AuraState(TypedDict):
    shadow_id: str
    biometrics: List[Dict]      # Recent snapshots from Neo4j
    aura_value: float           # Calculated [0.0 - 1.0]
    history: Annotated[List[Dict], operator.add]
    proposal: str               # The generated metaphor
    safety_consensus: Dict      # Verdicts from Triple-Lock
    crisis_level: str           # GREEN, YELLOW, RED (Redline)

def review_langgraph_schema():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")
    
    prompt = f"""
    As the Lead AI Architect, review this LangGraph State Schema for the Soft Recovery Agency (SRA).
    
    SCHEMA:
    {AuraState.__annotations__}
    
    Context:
    The AI must generate metaphors based on biometric history while ensuring 'Redline' safety.
    
    Question: 
    1. Is 'biometrics' as a List of Dicts sufficient for the 'Triple-Lock' to judge clinical safety?
    2. Should we separate 'Clinical_Observations' from 'Creative_Metaphors' in the state to avoid cross-contamination?
    """
    
    print(model.invoke(prompt).content)

if __name__ == "__main__":
    review_langgraph_schema()
