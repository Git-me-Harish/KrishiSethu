"""Voice NLU (Natural Language Understanding) — intent classification.

In production, this uses Google MuRIL (Multilingual Representations for
Indian Languages) fine-tuned for intent classification.

Supported intents:
- check_weather: "What's the weather at my field?"
- report_disease: "Identify this crop disease"
- check_scheme_eligibility: "Am I eligible for PM-Kisan?"
- view_insurance: "Show my insurance policies"
- check_ndvi: "What's the NDVI of my plot?"
- browse_marketplace: "Show me seeds for rice"
- check_soil: "What's my soil test result?"
- list_plots: "Show my plots"
- general_help: "How do I use this app?"

In development, uses keyword matching as a lightweight stub.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from krishisetu_ml.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class NLUResult:
    """Result of natural language understanding."""

    intent: str
    confidence: float
    entities: dict[str, Any]
    language: str
    inference_time_ms: int


# Intent keywords (multilingual)
INTENT_KEYWORDS: dict[str, list[str]] = {
    "check_weather": [
        "weather", "temperature", "rain", "forecast", "climate",
        "मौसम", "हवामान", "வானிலை", "వాతావరణ", "আবহাওয়া",
        "ಹವಾಮಾನ", "હવામાન", "ਮੌਸਮ", "കാലാവസ്ഥ",
    ],
    "report_disease": [
        "disease", "pest", "infection", "yellow leaf", "blight", "rust",
        "रोग", "कीड़ा", "बीमारी", "रोग पहचान", "फफूंद",
        "நோய்", "వ్యాధి", "রোগ", "ರೋಗ", "રોગ", "ਬੀਮਾਰੀ", "രോഗം",
    ],
    "check_scheme_eligibility": [
        "scheme", "pm-kisan", "kisan", "eligible", "subsidy", "benefit",
        "योजना", "पात्र", "सब्सिडी", "लाभ", "पीएम-किसान",
        "திட்டம்", "పథకం", "যোজনা", "ಯೋಜನೆ", "યોજના", "ਯੋਜਨਾ", "പദ്ധതി",
    ],
    "view_insurance": [
        "insurance", "policy", "claim", "premium", "pmfby",
        "बीमा", "नीति", "दावा", "प्रीमियम",
        "காப்பீடு", "భీమా", "বীমা", "ವಿಮಾ", "વીમા", "ਬੀਮਾ", "ഇൻഷുറൻസ്",
    ],
    "check_ndvi": [
        "ndvi", "satellite", "vegetation", "crop health",
        "एनडीवीआई", "उपग्रह", "फसल स्वास्थ्य",
    ],
    "browse_marketplace": [
        "buy", "order", "seed", "fertilizer", "pesticide", "marketplace", "shop",
        "खरीद", "बीज", "उर्वरक", "कीटनाशक", "ऑर्डर",
        "வாங்க", "కొనుగోలు", "কিনুন", "ಖರೀದಿ", "ખરીદી", "ਖਰੀਦੋ", "വാങ്ങുക",
    ],
    "check_soil": [
        "soil", "ph", "nutrient", "nitrogen", "fertilizer recommendation",
        "मिट्टी", "पीएच", "पोषक", "नाइट्रोजन",
        "மண்", "నేల", "মাটি", "ಮಣ್ಣು", "માટી", "ਮਿੱਟੀ", "മണ്ണ്",
    ],
    "list_plots": [
        "plot", "field", "land", "my plots", "farm",
        "खेत", "जमीन", "खेती",
        "வயல்", "పొలం", "জমি", "ಭೂಮಿ", "જમીન", "ਜ਼ਮੀਨ", "സ്ഥലം",
    ],
    "general_help": [
        "help", "how", "what can you do", "guide",
        "मदद", "सहायता", "कैसे",
        "உதவி", "సహాయం", "সাহায্য", "ಸಹಾಯ", "મદદ", "ਮਦਦ", "സഹായം",
    ],
}


class VoiceNLU:
    """Voice NLU model wrapper.

    In production: MuRIL fine-tuned for intent classification.
    In development: keyword-based matching.
    """

    def __init__(self) -> None:
        self._model = None
        self._is_loaded = False

    @property
    def is_available(self) -> bool:
        return self._is_loaded

    def load_model(self) -> None:
        """Load the MuRIL model (lazy)."""
        if self._is_loaded:
            return
        # In production: load MuRIL model
        logger.info("voice.nlu.model_load_skipped", reason="development_mode")
        self._is_loaded = False

    async def understand(self, text: str, language: str = "en") -> NLUResult:
        """Classify intent and extract entities from text.

        Args:
            text: Input text (transcribed from speech or typed)
            language: Language code of the text

        Returns:
            NLUResult with intent, confidence, entities, and language.
        """
        start_time = time.perf_counter()

        if not self.is_available:
            return self._keyword_match(text, language)

        # In production:
        # inputs = self._tokenizer(text, return_tensors="pt")
        # outputs = self._model(**inputs)
        # intent = self._id2label[outputs.logits.argmax().item()]
        # return NLUResult(intent=intent, ...)
        return self._keyword_match(text, language)

    def _keyword_match(self, text: str, language: str) -> NLUResult:
        """Keyword-based intent matching (dev mode)."""
        text_lower = text.lower()
        best_intent = "general_help"
        best_score = 0

        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > best_score:
                best_score = score
                best_intent = intent

        # Confidence based on match quality
        confidence = min(0.95, 0.5 + best_score * 0.15) if best_score > 0 else 0.3

        # Extract entities (simplified)
        entities: dict[str, Any] = {}
        if best_intent == "check_weather":
            entities["target"] = "current_plot"
        elif best_intent == "check_scheme_eligibility":
            if "pm-kisan" in text_lower or "पीएम-किसान" in text_lower:
                entities["scheme_code"] = "pm-kisan"
        elif best_intent == "browse_marketplace":
            for crop in ["rice", "wheat", "cotton", "maize", "बीज", "उर्वरक"]:
                if crop in text_lower:
                    entities["search_term"] = crop
                    break

        return NLUResult(
            intent=best_intent,
            confidence=confidence,
            entities=entities,
            language=language,
            inference_time_ms=int((time.perf_counter() - 1) * 1000),
        )


# Singleton
_nlu: VoiceNLU | None = None


def get_voice_nlu() -> VoiceNLU:
    global _nlu
    if _nlu is None:
        _nlu = VoiceNLU()
    return _nlu
