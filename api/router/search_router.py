from fastapi import APIRouter, Query

router = APIRouter()

@router.get("/search")
def search(
    query: str,
    k: int = Query(default=3, ge=1, le=20)
):
    return {
        "query": query,
        "results": []
    }
