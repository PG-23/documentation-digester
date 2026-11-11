from fastapi import APIRouter, HTTPException, Query, Request, Depends
from langchain_chroma import Chroma
import time

router = APIRouter()

def get_vector_store(request: Request):
    return request.app.state.vector_store

@router.get("/search")
async def search(
    query: str,
    k: int = Query(default=3, ge=1, le=20),
    vector_store: Chroma = Depends(get_vector_store)
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
    start_time = time.perf_counter()

    docs = await vector_store.asimilarity_search_with_relevance_scores(query, k)

    execution = time.perf_counter() - start_time
    
    return {
        "query": query,
        "results": [{
                "text": doc.page_content,
                "score": score,
                "title": doc.metadata.get("title", ""),
                "url": doc.metadata.get("url", ""),
                "source_file": doc.metadata.get("source_file", ""),
                "chunk_index": doc.metadata.get("chunk_index", ""),
                "section": doc.metadata.get("section", "")
            } for doc, score in docs
        ],
        "execution_time": execution
    }
