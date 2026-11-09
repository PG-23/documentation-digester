from fastapi import FastAPI
from .router.search_router import router as search_router

app = FastAPI()

app.include_router(search_router)