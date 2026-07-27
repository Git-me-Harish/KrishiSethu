"""Voice routes.

Endpoints:
- POST /voice/query       — Full voice query (audio → ASR → NLU → text response)
- POST /voice/nlu         — Text-based intent classification (no audio)
- POST /voice/tts         — Text-to-speech (generates audio from text)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from krishisetu.core.dependencies import CurrentUser, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import PERM_VOICE_QUERY
from krishisetu.domains.voice import services
from krishisetu.domains.voice.schemas import (
    NLURequest,
    NLUResponse,
    TTSRequest,
    VoiceQueryResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post(
    "/query",
    response_model=VoiceQueryResponse,
    dependencies=[Depends(require_permissions(PERM_VOICE_QUERY))],
)
async def voice_query(
    current_user: CurrentUser,
    file: UploadFile = File(..., description="Audio file (WAV, MP3, WebM)"),
    language: str | None = None,
) -> VoiceQueryResponse:
    """Process a voice query.

    1. Sends audio to ML inference service for ASR (speech-to-text)
    2. Classifies intent from transcribed text (NLU)
    3. Generates a text response based on the intent
    4. (Phase 2) Generates TTS audio response

    Returns the transcribed text, intent, and response text.
    """
    # Validate content type
    allowed = {
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/mpeg", "audio/mp3",
        "audio/webm", "audio/ogg",
        "audio/mp4",
    }
    if file.content_type not in allowed:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported audio format: {file.content_type}. "
                f"Allowed: {', '.join(sorted(allowed))}"
            ),
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large (max 10MB)",
        )

    # Use farmer's preferred language if not specified
    if not language and current_user.preferred_language:
        language = current_user.preferred_language

    try:
        result = await services.process_voice_query(
            audio_bytes, file.content_type, language=language
        )
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    logger.info(
        "voice.query.completed",
        farmer_id=str(current_user.id),
        intent=result.intent,
        language=result.detected_language,
        time_ms=result.total_time_ms,
    )

    return result


@router.post(
    "/nlu",
    response_model=NLUResponse,
    dependencies=[Depends(require_permissions(PERM_VOICE_QUERY))],
)
async def classify_intent(payload: NLURequest) -> NLUResponse:
    """Classify intent from text (no audio).

    Useful for typed queries or testing NLU without audio.
    """
    try:
        result = await services.classify_text_intent(payload.text, payload.language)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    return result


@router.post(
    "/tts",
    dependencies=[Depends(require_permissions(PERM_VOICE_QUERY))],
)
async def text_to_speech(
    payload: TTSRequest,
    current_user: CurrentUser,
) -> dict:
    """Generate speech from text (text-to-speech).

    Phase 2: Will use Azure Cognitive Services Speech API for natural voices
    in 10 Indian languages. Currently returns text-only (no audio).
    """
    # Use farmer's preferred language if not specified
    language = payload.language
    if language == "en" and current_user.preferred_language:
        language = current_user.preferred_language

    audio_url = await services.generate_tts(payload.text, language=language)

    return {
        "text": payload.text,
        "language": language,
        "audio_url": audio_url,
        "available": audio_url is not None,
    }
