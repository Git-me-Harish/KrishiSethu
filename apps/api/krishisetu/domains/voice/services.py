"""Voice service — bridges frontend to ML inference service for ASR/NLU/TTS."""

from __future__ import annotations

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.domains.voice.schemas import (
    NLUResponse,
    VoiceQueryResponse,
)

logger = get_logger(__name__)


async def process_voice_query(
    audio_bytes: bytes,
    content_type: str,
    language: str | None = None,
) -> VoiceQueryResponse:
    """Process a voice query: send audio to ML service, get ASR + NLU + response.

    The ML service handles:
    1. ASR (speech-to-text) using Whisper
    2. NLU (intent classification) using MuRIL
    3. Response text generation

    TTS (text-to-speech) is handled separately via the TTS endpoint.
    """
    ml_url = settings().ML_INFERENCE_URL.rstrip("/")
    endpoint = f"{ml_url}/voice/query"
    timeout = 30

    # Determine file extension from content type
    ext_map = {
        "audio/wav": "wav", "audio/wave": "wav", "audio/x-wav": "wav",
        "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/webm": "webm", "audio/ogg": "ogg",
        "audio/mp4": "mp4",
    }
    ext = ext_map.get(content_type, "wav")

    params = {}
    if language:
        params["language"] = language

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                endpoint,
                files={"file": (f"audio.{ext}", audio_bytes, content_type)},
                params=params,
                headers={
                    "X-ML-Service-Token": settings().ML_SERVICE_TOKEN.get_secret_value()
                },
            )
        except httpx.ConnectError as e:
            logger.error("voice.ml_service_unavailable", error=str(e))
            raise RuntimeError("Voice service is unavailable. Please try again later.") from e
        except httpx.TimeoutException as e:
            logger.error("voice.ml_service_timeout", error=str(e))
            raise RuntimeError("Voice service timed out. Please try again.") from e

    if response.status_code != 200:
        logger.error(
            "voice.ml_service_error",
            status=response.status_code,
            body=response.text[:200],
        )
        raise RuntimeError(f"Voice service error: {response.status_code}")

    data = response.json()

    return VoiceQueryResponse(
        transcribed_text=data["transcribed_text"],
        detected_language=data["detected_language"],
        intent=data["intent"],
        intent_confidence=data["intent_confidence"],
        entities=data.get("entities", {}),
        response_text=data["response_text"],
        total_time_ms=data["total_time_ms"],
    )


async def classify_text_intent(
    text: str, language: str = "en"
) -> NLUResponse:
    """Classify intent from text (no audio — for typed queries)."""
    ml_url = settings().ML_INFERENCE_URL.rstrip("/")
    endpoint = f"{ml_url}/voice/nlu"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            endpoint,
            json={"text": text, "language": language},
            headers={
                "X-ML-Service-Token": settings().ML_SERVICE_TOKEN.get_secret_value()
            },
        )

    if response.status_code != 200:
        raise RuntimeError(f"NLU service error: {response.status_code}")

    data = response.json()
    return NLUResponse(
        intent=data["intent"],
        confidence=data["confidence"],
        entities=data.get("entities", {}),
        language=data.get("language", language),
    )


async def generate_tts(
    text: str, language: str = "en"
) -> str | None:
    """Generate text-to-speech audio.

    In production, this calls Azure Cognitive Services Speech API.
    In development, returns None (frontend displays text only).

    Returns:
        URL to the generated audio file, or None if TTS is unavailable.
    """
    # Phase 2: Azure TTS integration
    # For now, return None — the frontend displays the text response
    logger.info("voice.tts.skipped", reason="not_configured", language=language)
    return None
