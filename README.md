# Documentation Digester
Semantic search over a subset of the Godot docs.

## Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

## Build the index
python -m ingest.ingest --reset

## Run the API
uvicorn api.main:app --reload
# then open http://localhost:8000/docs

## Team
| Role | Owner |
|---|---|
| Ingestion pipeline + vector DB | Patrick |
| Search API + metadata | Dennis |
| Data prep | Gbola |
| Integration / demo lead | Sohan |
| Chunking | Yashvi |
| Evaluation | Gian |
| Frontend UI | Monzerrat |