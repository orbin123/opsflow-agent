"""Read-only reminder catalogue; scheduling and delivery are separate utilities."""

from fastapi import APIRouter, HTTPException

from app.reminder_catalogue import SavedReminder, list_saved_reminders
from app.tools.reminders import ReminderPersistenceError


router = APIRouter(prefix="/api/v1")


@router.get("/reminders", response_model=list[SavedReminder])
def get_reminders():
    try:
        return list_saved_reminders()
    except ReminderPersistenceError:
        raise HTTPException(status_code=503, detail="Saved reminders could not be loaded") from None
