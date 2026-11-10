from fastapi import APIRouter, Query, Request, Depends
from langchain_chroma import Chroma

router = APIRouter()

def get_vector_store(request: Request):
    return request.app.state.vector_store

@router.get("/search")
async def search(
    query: str,
    k: int = Query(default=3, ge=1, le=20),
    vector_store: Chroma = Depends(get_vector_store)
):

    docs = await vector_store.asimilarity_search_with_relevance_scores(query, k)
    
    return {
        "query": query,
        "results": [{
                "text": doc.page_content,
                "score": score,
                "title": doc.metadata.get("title", ""),
                "url": doc.metadata.get("url", ""),
                "source_file": doc.metadata.get("source_file", ""),
                "chunk_index": doc.metadata.get("chunk_index", "")
            } for doc, score in docs
        ]
    }
