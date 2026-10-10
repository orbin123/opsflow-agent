"""Identity of the one trusted local employee workspace; not authentication."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PROFILE_ID = "EMP-001"


class EmployeeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    profile_id: Literal["EMP-001"]
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    company: str = Field(min_length=1)
    timezone: Literal["Asia/Kolkata"]
    is_demo: Literal[True]
