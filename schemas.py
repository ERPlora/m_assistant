from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str = ""
    context: str = Field(default="general", pattern="^(general|setup)$")


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str


class ConfirmActionResponse(BaseModel):
    success: bool
    message: str


class SkipSetupResponse(BaseModel):
    success: bool
    redirect_url: str = "/"
