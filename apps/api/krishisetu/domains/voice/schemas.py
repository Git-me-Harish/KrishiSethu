"""Pydantic schemas for the voice domain."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceQueryResponse(BaseModel):
    """Response from a voice query (ASR → NLU → text response)."""

    transcribed_text: str = Field(..., description="What the farmer said (transcribed)")
    detected_language: str = Field(..., description="Detected language code")
    intent: str = Field(..., description="Classified intent")
    intent_confidence: float = Field(..., description="NLU confidence [0, 1]")
    entities: dict = Field(default_factory=dict, description="Extracted entities")
    response_text: str = Field(..., description="Text response to display/speak")
    audio_response_url: str | None = Field(
        default=None,
        description="Pre-signed URL for TTS audio response (if TTS available)",
    )
    total_time_ms: int = Field(..., description="Total processing time in ms")


class NLURequest(BaseModel):
    """Request for text-based NLU (no audio)."""

    text: str = Field(..., min_length=1, max_length=1000)
    language: str = Field(default="en")


class NLUResponse(BaseModel):
    """NLU result."""

    intent: str
    confidence: float
    entities: dict
    language: str


class TTSRequest(BaseModel):
    """Request for text-to-speech."""

    text: str = Field(..., min_length=1, max_length=2000)
    language: str = Field(default="en", description="Language code for voice selection")
