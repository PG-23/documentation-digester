from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from .router.search_router import router as search_router
from .router.ingestion_router import router as ingestion_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        encode_kwargs={"normalize_embeddings": True}
    )

    app.state.vector_store = Chroma(
        collection_name="godot_docs",
        embedding_function=embeddings,
        persist_directory="chroma_db/"
    )

    yield

app = FastAPI(lifespan=lifespan) 

app.include_router(search_router)
app.include_router(ingestion_router)