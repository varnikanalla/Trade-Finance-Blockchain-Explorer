from pydantic import BaseModel
from app.models import UserRole

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: UserRole
    org_name: str

class LoginRequest(BaseModel):
    email: str
    password: str
