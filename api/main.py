from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from .router.search_router import router as search_router
from .router.ingestion_router import router as ingestion_router
from .router.operations_router import router as operations_router
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "chroma_db"

@asynccontextmanager
async def lifespan(app: FastAPI):

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )

    app.state.vector_store = Chroma(
        collection_name="godot_docs",
        embedding_function=embeddings,
        persist_directory=DB_PATH
    )

    yield

app = FastAPI(lifespan=lifespan) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(ingestion_router)
app.include_router(operations_router)