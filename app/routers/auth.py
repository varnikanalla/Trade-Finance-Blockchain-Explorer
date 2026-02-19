from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.database import get_session
from app.models import User
from app.schemas import UserCreate, LoginRequest
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter()

@router.post("/signup")
def signup(data: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == data.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        role=data.role,
        org_name=data.org_name
    )
    session.add(user)
    session.commit()
    return {"message": "User registered successfully"}

@router.post("/login")
def login(data: LoginRequest, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == data.email)).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": user.email,
        "name": user.name,
        "role": user.role,
        "org": user.org_name
    })
    return {"access_token": token}
