from fastapi import APIRouter, Depends
from app.dependencies import get_current_user

router = APIRouter()

@router.get("/me")
def profile(user=Depends(get_current_user)):
    return {
        "name": user["name"],
        "email": user["sub"],
        "org": user["org"],
        "role": user["role"]
    }
