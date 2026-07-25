"""Voice ASR (Automatic Speech Recognition) model wrapper.

In production, this wraps OpenAI Whisper large-v3 fine-tuned on Indic speech.
In development, it provides a text-based stub that returns a predefined
query based on the audio file name.

The ASR model handles 10 Indian languages:
- Hindi, Marathi, Tamil, Telugu, Bengali, Kannada, Gujarati, Punjabi, Malayalam
- English (Indian accent)

Whisper is self-hosted on the ML inference service for data residency.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Any

from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ASRResult:
    """Result of speech recognition."""

    text: str
    language: str
    confidence: float
    inference_time_ms: int


class VoiceASR:
    """Voice ASR model wrapper.

    In production (Whisper model loaded), transcribes audio to text.
    In development, returns a stub transcription for testing.
    """

    # Supported languages (ISO 639-1 codes)
    SUPPORTED_LANGUAGES = {
        "en", "hi", "mr", "ta", "te", "bn", "kn", "gu", "pa", "ml",
    }

    def __init__(self) -> None:
        self._model = None
        self._is_loaded = False

    @property
    def is_available(self) -> bool:
        """Whether the Whisper model is loaded."""
        return self._is_loaded

    def load_model(self) -> None:
        """Load the Whisper model (lazy initialization)."""
        if self._is_loaded:
            return

        try:
            # In production: import whisper; self._model = whisper.load_model("large-v3")
            # For now, we use a stub
            logger.info("voice.asr.model_load_skipped", reason="development_mode")
            self._is_loaded = False
        except Exception as e:
            logger.warning("voice.asr.model_load_failed", error=str(e))
            self._is_loaded = False

    async def transcribe(
        self, audio_bytes: bytes, language: str | None = None
    ) -> ASRResult:
        """Transcribe audio to text.

        Args:
            audio_bytes: Audio file bytes (WAV, MP3, etc.)
            language: Optional language hint (ISO 639-1). If None, auto-detect.

        Returns:
            ASRResult with transcribed text, detected language, and confidence.
        """
        start_time = time.perf_counter()

        if not self.is_available:
            # Dev mode stub — return a common query
            return self._stub_transcribe(audio_bytes, language)

        try:
            # In production:
            # import whisper
            # audio = whisper.load_audio(io.BytesIO(audio_bytes))
            # result = self._model.transcribe(audio, language=language)
            # return ASRResult(
            #     text=result["text"],
            #     language=result.get("language", "en"),
            #     confidence=result.get("avg_logprob", 0.0),
            #     inference_time_ms=int((time.perf_counter() - start_time) * 1000),
            # )
            return self._stub_transcribe(audio_bytes, language)
        except Exception as e:
            logger.error("voice.asr.transcribe_failed", error=str(e))
            raise

    def _stub_transcribe(
        self, audio_bytes: bytes, language: str | None
    ) -> ASRResult:
        """Stub transcription for development mode.

        Returns a common farmer query based on audio size (deterministic).
        """
        # Use audio length as a pseudo-seed for deterministic stub
        audio_len = len(audio_bytes)
        queries = [
            "What's the weather at my field today?",
            "माझ्या शेतात आज हवामान कसे आहे?",  # Marathi
            "Identify this crop disease",
            "Am I eligible for PM-Kisan?",
            "Show my insurance policies",
            "What's the NDVI of my plot?",
            "मेरे खेत में मौसम कैसा है?",  # Hindi
        ]

        query_index = audio_len % len(queries)
        text = queries[query_index]

        # Detect language from text (simplified)
        lang = language or self._detect_language_from_text(text)

        return ASRResult(
            text=text,
            language=lang,
            confidence=0.95,
            inference_time_ms=150,
        )

    def _detect_language_from_text(self, text: str) -> str:
        """Detect language from text script (simplified)."""
        # Check for Devanagari (Hindi, Marathi)
        if any("\u0900" <= c <= "\u097F" for c in text):
            return "hi"  # Default to Hindi for Devanagari
        # Check for Tamil
        if any("\u0B80" <= c <= "\u0BFF" for c in text):
            return "ta"
        # Check for Telugu
        if any("\u0C00" <= c <= "\u0C7F" for c in text):
            return "te"
        # Check for Bengali
        if any("\u0980" <= c <= "\u09FF" for c in text):
            return "bn"
        # Check for Kannada
        if any("\u0C80" <= c <= "\u0CFF" for c in text):
            return "kn"
        # Check for Gujarati
        if any("\u0A80" <= c <= "\u0AFF" for c in text):
            return "gu"
        # Check for Gurmukhi (Punjabi)
        if any("\u0A00" <= c <= "\u0A7F" for c in text):
            return "pa"
        # Check for Malayalam
        if any("\u0D00" <= c <= "\u0D7F" for c in text):
            return "ml"
        return "en"  # Default


# Singleton
_asr: VoiceASR | None = None


def get_voice_asr() -> VoiceASR:
    global _asr
    if _asr is None:
        _asr = VoiceASR()
    return _asr
