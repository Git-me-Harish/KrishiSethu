"""Voice endpoints for the ML inference service.

POST /voice/asr — Transcribe audio to text
POST /voice/nlu — Classify intent from text
POST /voice/query — Full pipeline: ASR → NLU → response (text)
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from krishisetu_ml.core.logging import get_logger
from krishisetu_ml.core.uploads import read_upload_limited
from krishisetu_ml.models.voice_asr import get_voice_asr
from krishisetu_ml.models.voice_nlu import get_voice_nlu

logger = get_logger(__name__)

MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

router = APIRouter(prefix="/voice", tags=["voice"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ASRResponse(BaseModel):
    """Speech recognition result."""

    text: str = Field(..., description="Transcribed text")
    language: str = Field(..., description="Detected language code")
    confidence: float = Field(..., description="Confidence score [0, 1]")
    inference_time_ms: int = Field(..., description="Processing time in ms")


class NLURequest(BaseModel):
    """Request for NLU (text → intent)."""

    text: str = Field(..., min_length=1, max_length=1000)
    language: str = Field(default="en", description="Language code of the text")


class NLUResponse(BaseModel):
    """NLU result."""

    intent: str = Field(..., description="Classified intent")
    confidence: float = Field(...)
    entities: dict[str, Any] = Field(default_factory=dict)
    language: str
    inference_time_ms: int


class VoiceQueryResponse(BaseModel):
    """Full voice query response (ASR + NLU + text response)."""

    transcribed_text: str
    detected_language: str
    intent: str
    intent_confidence: float
    entities: dict[str, Any]
    response_text: str = Field(..., description="Text response to be spoken via TTS")
    total_time_ms: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/asr", response_model=ASRResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file (WAV, MP3, WebM)"),
    language: str | None = None,
) -> ASRResponse:
    """Transcribe audio to text using Whisper ASR.

    Supports 10 Indian languages. If language is not specified, auto-detects.
    """
    if file.content_type not in (
        "audio/wav", "audio/wave", "audio/x-wav",
        "audio/mpeg", "audio/mp3",
        "audio/webm", "audio/ogg",
        "audio/mp4",
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio format: {file.content_type}",
        )

    # Streamed read: aborts as soon as the running total crosses the limit,
    # so an oversized body can never be buffered in full.
    audio_bytes = await read_upload_limited(file, MAX_AUDIO_SIZE_BYTES)

    asr = get_voice_asr()
    result = await asr.transcribe(audio_bytes, language=language)

    logger.info(
        "voice.asr.completed",
        text=result.text[:100],
        language=result.language,
        confidence=result.confidence,
        time_ms=result.inference_time_ms,
    )

    return ASRResponse(
        text=result.text,
        language=result.language,
        confidence=result.confidence,
        inference_time_ms=result.inference_time_ms,
    )


@router.post("/nlu", response_model=NLUResponse)
async def classify_intent(payload: NLURequest) -> NLUResponse:
    """Classify intent from text using MuRIL NLU.

    Returns the classified intent, confidence, and extracted entities.
    """
    nlu = get_voice_nlu()
    result = await nlu.understand(payload.text, language=payload.language)

    logger.info(
        "voice.nlu.completed",
        intent=result.intent,
        confidence=result.confidence,
        text=payload.text[:100],
        time_ms=result.inference_time_ms,
    )

    return NLUResponse(
        intent=result.intent,
        confidence=result.confidence,
        entities=result.entities,
        language=result.language,
        inference_time_ms=result.inference_time_ms,
    )


@router.post("/query", response_model=VoiceQueryResponse)
async def voice_query(
    file: UploadFile = File(..., description="Audio file"),
    language: str | None = None,
) -> VoiceQueryResponse:
    """Full voice query pipeline: ASR → NLU → text response.

    1. Transcribes audio to text (ASR)
    2. Classifies intent from text (NLU)
    3. Generates a text response based on the intent

    The text response can then be converted to speech via TTS (handled by
    the main API service, not the ML inference service).
    """
    start_time = time.perf_counter()

    audio_bytes = await read_upload_limited(file, MAX_AUDIO_SIZE_BYTES)

    # Step 1: ASR
    asr = get_voice_asr()
    asr_result = await asr.transcribe(audio_bytes, language=language)

    # Step 2: NLU
    nlu = get_voice_nlu()
    nlu_result = await nlu.understand(asr_result.text, language=asr_result.language)

    # Step 3: Generate response text
    response_text = _generate_response(nlu_result.intent, nlu_result.entities, asr_result.language)

    total_ms = int((time.perf_counter() - start_time) * 1000)

    logger.info(
        "voice.query.completed",
        transcribed_text=asr_result.text[:100],
        intent=nlu_result.intent,
        confidence=nlu_result.confidence,
        total_time_ms=total_ms,
    )

    return VoiceQueryResponse(
        transcribed_text=asr_result.text,
        detected_language=asr_result.language,
        intent=nlu_result.intent,
        intent_confidence=nlu_result.confidence,
        entities=nlu_result.entities,
        response_text=response_text,
        total_time_ms=total_ms,
    )


# ---------------------------------------------------------------------------
# Response generation
# ---------------------------------------------------------------------------


def _generate_response(intent: str, entities: dict[str, Any], language: str) -> str:
    """Generate a text response based on intent and entities.

    In production, this would call the main API to fetch actual data
    (weather, schemes, etc.) and format a natural language response.

    For now, returns a template-based response.
    """
    responses: dict[str, dict[str, str]] = {
        "check_weather": {
            "en": "Let me check the weather at your field. Please open the Weather section in the dashboard for detailed conditions and forecast.",
            "hi": "आपके खेत का मौसम जांचने दें। विस्तृत स्थिति और पूर्वानुमान के लिए कृपया डैशबोर्ड में मौसम अनुभाग खोलें।",
        },
        "report_disease": {
            "en": "To identify a crop disease, please open the Disease Identification section and upload a photo of the affected plant.",
            "hi": "फसल रोग की पहचान के लिए, कृपया रोग पहचान अनुभाग खोलें और प्रभावित पौधे की फोटो अपलोड करें।",
        },
        "check_scheme_eligibility": {
            "en": "Let me check your scheme eligibility. Please open the Government Schemes section to see all schemes you are eligible for.",
            "hi": "आपकी योजना पात्रता जांचने दें। आप जिन सभी योजनाओं के लिए पात्र हैं, उन्हें देखने के लिए कृपया सरकारी योजनाएं अनुभाग खोलें।",
        },
        "view_insurance": {
            "en": "Your insurance policies are in the Insurance section. Open it to view your active policies and claims.",
            "hi": "आपकी बीमा नीतियां बीमा अनुभाग में हैं। अपनी सक्रिय नीतियां और दावे देखने के लिए इसे खोलें।",
        },
        "check_ndvi": {
            "en": "Your plot's NDVI data is in the NDVI Monitoring section. Open it to see the latest vegetation health.",
            "hi": "आपके खेत का एनडीवीआई डेटा एनडीवीआई निगरानी अनुभाग में है। नवीनतम वनस्पति स्वास्थ्य देखने के लिए इसे खोलें।",
        },
        "browse_marketplace": {
            "en": "You can browse and order agricultural inputs in the Marketplace section.",
            "hi": "आप बाजार अनुभाग में कृषि इनपुट ब्राउज़ और ऑर्डर कर सकते हैं।",
        },
        "check_soil": {
            "en": "Your soil test results are in the Soil Health section. Open it to see nutrient levels and recommendations.",
            "hi": "आपके मिट्टी परीक्षण परिणाम मिट्टी स्वास्थ्य अनुभाग में हैं। पोषक स्तर और सिफारिशें देखने के लिए इसे खोलें।",
        },
        "list_plots": {
            "en": "Your registered plots are in the My Plots section. Open it to see all your fields.",
            "hi": "आपके पंजीकृत खेत मेरे खेत अनुभाग में हैं। अपने सभी खेत देखने के लिए इसे खोलें।",
        },
        "general_help": {
            "en": "I can help you with: checking weather, identifying crop diseases, finding government schemes, viewing insurance, checking NDVI, browsing the marketplace, and viewing soil test results. What would you like to do?",
            "hi": "मैं आपकी मदद कर सकता हूं: मौसम जांचना, फसल रोग की पहचान, सरकारी योजनाएं खोजना, बीमा देखना, एनडीवीआई जांचना, बाजार ब्राउज़ करना, और मिट्टी परीक्षण परिणाम देखना। आप क्या करना चाहेंगे?",
        },
    }

    lang = language if language in {"hi"} else "en"
    return responses.get(intent, responses["general_help"]).get(lang, responses["general_help"]["en"])
