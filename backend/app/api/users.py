"""User management routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import hash_password
from app.models.user import User
from app.schemas.base import GenericResponse
from app.schemas.user import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=GenericResponse[UserResponse])
async def create_user(request: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(400, "Username already exists")
    user = User(username=request.username, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return GenericResponse(data=_to_response(user))


@router.get("/{user_id}", response_model=GenericResponse[UserResponse])
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return GenericResponse(data=_to_response(user))


@router.get("", response_model=GenericResponse[list[UserResponse]])
async def list_users(db: Session = Depends(get_db)):
    users = db.query(User).filter(User.is_active.is_(True)).all()
    return GenericResponse(data=[_to_response(u) for u in users])


@router.put("/{user_id}", response_model=GenericResponse[UserResponse])
async def update_user(
    user_id: int, request: UserUpdate, db: Session = Depends(get_db)
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if request.username:
        user.username = request.username
    if request.password:
        user.password_hash = hash_password(request.password)
    db.commit()
    db.refresh(user)
    return GenericResponse(data=_to_response(user))


@router.post("/{user_id}/disable", response_model=GenericResponse)
async def disable_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    user.is_active = False
    db.commit()
    return GenericResponse(msg="user disabled")


def _to_response(u: User) -> UserResponse:
    return UserResponse(
        id=u.id, username=u.username, is_active=u.is_active, role=u.role,
        created_at=u.created_at,
    )
