from sqlmodel import SQLModel, Field
from enum import Enum
from typing import Optional
from datetime import datetime

class UserRole(str, Enum):
    bank = "bank"
    corporate = "corporate"
    auditor = "auditor"
    admin = "admin"

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password: str
    role: UserRole
    org_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
