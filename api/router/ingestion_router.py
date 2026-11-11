from pathlib import Path
import time
from fastapi import APIRouter, HTTPException

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
def ingestion(place: str | None = None):
    start_time = time.perf_counter()

    collection = get_collection(reset=False)
    model = get_model()

    if place is None or place.lower() == "docs":
        folder = DOCS_DIR
    elif place.lower() == "holdout":
        folder = HOLDOUT_DIR
    else:
        raise HTTPException(status_code=400, detail="Please use the built in files to query.")

    count_before = collection.count()

    documents = load_documents(folder)
    returned = ingest_documents(documents, collection, "semantic", model)

    count_after = collection.count()
    execution = time.perf_counter() - start_time

    return {
        "data": returned,
        "collection_before": count_before,
        "collection_after": count_after,
        "chunks_added": count_after - count_before,
        "execution_time": round(execution, 3),
    }