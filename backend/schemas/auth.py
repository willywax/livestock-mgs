"""Login, token and user schemas."""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

from models import UserRole


# Auth schemas
class UserLogin(BaseModel):
    phone: str
    password: str

class UserCreate(BaseModel):
    phone: str
    password: str
    name: str
    role: UserRole = UserRole.VIEWER

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    phone: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
