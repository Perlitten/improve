from langchain_nvidia_ai_endpoints import ChatNVIDIA

def review_backend_structure():
    model = ChatNVIDIA(model="meta/llama-3.1-405b-instruct")
    
    structure = """
    d:/SRA/backend/
    ├── app/
    │   ├── api/          # REST Endpoints (FastAPI)
    │   ├── core/         # Config, Security, Constants
    │   ├── grpc/         # gRPC Servicers & Protos
    │   ├── models/       # Pydantic & SQLAlchemy Models
    │   ├── services/     # Business Logic (Identity, GraphRAG, AI)
    │   ├── db/           # Neo4j & Postgres Connectors
    │   └── main.py
    ├── tests/            # Pytest suite (TDD)
    ├── requirements.txt
    └── .env
    """
    
    prompt = f"""
    As the Lead Architect, review this FastAPI structure for SRA. 
    It must support:
    1. Split-Key Identity Vault.
    2. High-frequency gRPC biometric ingestion.
    3. GraphRAG reasoning (Neo4j).
    
    Is 'services/' sufficient for AI orchestration or should we have a dedicated 'ai_engine/' module?
    Where should we put the 'Triple-Consensus' logic?
    """
    
    print(model.invoke(prompt).content)

if __name__ == "__main__":
    review_backend_structure()
