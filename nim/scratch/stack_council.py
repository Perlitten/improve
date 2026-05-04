import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import ChatNVIDIA

load_dotenv()

def stack_council():
    model = ChatNVIDIA(model="meta/llama-3.1-70b-instruct")

    print("\n--- [Council] Mobile Architect: Native Kotlin vs Cross-platform ---")
    mobile = model.invoke("Why is Native Android (Kotlin + Jetpack Compose) the best choice for SRA v1? Focus on Biometric integration (Health Connect), Haptic Feedback, and UI fluidity for the 'Aura' visualization. How does it compare to Flutter?").content
    print(mobile)

    print("\n--- [Council] Backend Architect: The Python vs Go Dilemma ---")
    backend = model.invoke(f"SRA needs GraphRAG (Neo4j) and heavy LLM orchestration (NIM). Should we use Python (FastAPI) for AI agility or Go for performance? Can we use a Hybrid approach (Go for data ingestion, Python for AI)? Suggest the 'Best' stack for P99 latency.\n\nContext: {mobile}").content
    print(backend)

    print("\n--- [Council] API Architect: gRPC vs REST for Biometrics ---")
    api = model.invoke(f"We have real-time biometric streams and 'Aura' snapshot updates. Is gRPC + Protobuf better than REST for SRA? How does it affect mobile battery and performance?\n\nContext: {backend}").content
    print(api)

if __name__ == "__main__":
    stack_council()
