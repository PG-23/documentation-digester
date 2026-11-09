from fastapi import APIRouter, Query, Request, Depends
from langchain_chroma import Chroma

router = APIRouter()

def get_vector_store(request: Request):
    return request.app.state.vector_store

@router.get("/search")
def search(
    query: str,
    k: int = Query(default=3, ge=1, le=20),
    vector_store: Chroma = Depends(get_vector_store)
):
    retriever = vector_store.as_retriever(
        search_kwargs={"k": k}
    )

    documents = retriever.invoke(query)
    
    return {
        "query": query,
        "results": [{
                "content": doc.page_content,
                "metadata": doc.metadata
            } for doc in documents
        ]
    }
