from fastapi import Header, HTTPException
from jose import jwt
from app.auth import SECRET_KEY, ALGORITHM

def get_current_user(token: str = Header(...)):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid token")
