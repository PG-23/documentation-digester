from pathlib import Path

from fastapi import APIRouter

from ingest.ingest import ingest_documents, load_documents, get_collection, get_model

router = APIRouter()

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "data" / "docs"
HOLDOUT_DIR = ROOT / "data" / "holdout"

"""
To empty the chroma database to test the ingestion pipeline use:
```
python -c "from ingest.ingest import get_collection; get_collection(reset=True)
```

By default this will load everything inside of the DOCS folder. 
HOLDOUT will hit the holdout directory for testing purposes
"""
@router.post("/ingestion")
async def ingestion(place: str | None = None):
    collection = get_collection(reset = False)
    model = get_model()

    if place is None or place == "DOCS":
        documents = load_documents(DOCS_DIR)
        returned = ingest_documents(documents, collection, "length", model)
    elif place == "HOLDOUT":
        documents = load_documents(HOLDOUT_DIR)
        returned = ingest_documents(documents, collection, "length", model)
    else:
        raise ValueError("Please use the built in files to query.")

    return {"status": 200, "data": returned}
