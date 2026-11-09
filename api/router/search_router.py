from fastapi import FastAPI, Query, APIRouter, Request, Depends
from langchain_chroma import Chroma
from langchain_core.language_models import BaseChatModel

router = APIRouter(prefix="/")

def get_vector_store(request: Request) -> Chroma: 
    # Add what the vector db store is
    pass

def get_llm_model(request: Request) -> BaseChatModel:
    # I think model is needed here idk
    pass

@router.get("/search")
def search(query: str, k: int, vector_store: Chroma = Depends(get_vector_store)):

    retriever = get_vector_store();

    documents = retriever.invoke(query)


    return {
        "query": query,
        "results": [{
            "content": doc.content,
            "metadata": doc.metadata
        } for doc in documents]
    }