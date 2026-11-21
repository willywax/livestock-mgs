"""Root endpoint."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "ShambaManager API", "version": "1.0.0"}
