from pathlib import Path
import time
import os
from fastapi import APIRouter, Form, HTTPException, File, UploadFile

from ingest.ingest import ingest_documents, load_documents, get_collection, get_model, ingest_text

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

@router.post("/ingest")
async def ingest_file(
    file: UploadFile = File(...),
    title: str = Form(...),
    section: str = Form(...),
    url: str = Form(...)
):
    # Get the text from the document
    extension = os.path.splitext(file.filename or "")[1].lower()

    # Check valid document
    if extension in {".txt", ".md"}:
        content = await file.read()
        text = content.decode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="Upload a .txt file")

    # Send Request
    collection = get_collection(reset=False)
    model = get_model()
    details = ingest_text(text, file.filename, title, section, url, collection, model, "semantic")

    # Return info
    return{
        "source_file": file.filename,
        "title": title,
        "chunks": details.get("chunks", 0),
        "seconds": details.get("seconds", 0),
        "collection_total": details.get("collection_total", 0)
    }