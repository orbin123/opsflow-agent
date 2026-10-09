"""Read the persistent singleton employee; never execute a chat or tool."""

from fastapi import APIRouter, HTTPException

from app.chat_store import ChatPersistenceError
from app.profile import EmployeeProfile
from app.sessions import get_profile


router = APIRouter(prefix="/api/v1")


@router.get("/profile", response_model=EmployeeProfile)
def employee_profile():
    try:
        return get_profile()
    except ChatPersistenceError:
        raise HTTPException(status_code=503, detail="Employee profile could not be loaded.") from None
