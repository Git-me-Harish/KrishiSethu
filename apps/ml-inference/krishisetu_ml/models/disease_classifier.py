"""Crop disease classifier — YOLOv8 ONNX wrapper.

This module wraps the YOLOv8 classification model exported to ONNX format.
It handles:
- Image preprocessing (resize, normalize, NCHW conversion)
- ONNX inference
- Postprocessing (softmax, top-k predictions, confidence calibration)

The model is a YOLOv8x-cls fine-tuned on PlantVillage + PlantDoc + custom
Indian crop disease dataset. See ml/registry/disease_classifier/card.md
for the full model card.

Training details (see ml/training/disease_classifier.py):
- Input: 640x640 RGB image, normalized to [0, 1]
- Output: logits over N disease classes
- Augmentation: rotation, flip, color jitter, random crop, blur
- Loss: focal loss with class weights (for imbalance)
- Calibration: temperature scaling applied to softmax

Class labels are loaded from settings.DISEASE_CLASSIFIER_LABELS and must
match the order used during training.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import get_logger
from krishisetu_ml.core.onnx_runtime import get_model_loader

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Input image size — must match training
INPUT_SIZE = 640

# ImageNet normalization (standard for YOLOv8)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Temperature scaling for confidence calibration
# (learned during training, see ml/training/calibrate.py)
TEMPERATURE = 1.5

# Minimum confidence to consider a prediction "reliable"
# Below this, the UI will prompt "Diagnosis uncertain — please consult an officer"
MIN_CONFIDENCE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Prediction:
    """A single disease prediction."""

    label: str
    confidence: float
    disease_slug: str  # URL-friendly identifier


@dataclass
class DiseasePredictionResult:
    """Full prediction result from the disease classifier."""

    top_prediction: Prediction
    all_predictions: list[Prediction]
    model_name: str
    model_version: str
    inference_time_ms: float
    is_reliable: bool  # True if confidence >= threshold


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class DiseaseClassifier:
    """Wraps the YOLOv8 disease classification ONNX model.

    Usage:
        classifier = DiseaseClassifier(session)
        result = classifier.predict(image)  # PIL.Image
    """

    def __init__(self, session) -> None:
        """Initialize with a loaded ONNX InferenceSession.

        Args:
            session: ONNX Runtime InferenceSession for the disease model.
        """
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.labels = settings().DISEASE_CLASSIFIER_LABELS
        self.model_version = settings().DISEASE_CLASSIFIER_MODEL_VERSION

        # Validate that the model output matches the number of labels
        output_shape = session.get_outputs()[0].shape
        if (
            len(output_shape) >= 2
            and isinstance(output_shape[-1], int)
            and output_shape[-1] != len(self.labels)
        ):
            logger.warning(
                "model.label_count_mismatch",
                model_output_classes=output_shape[-1],
                configured_labels=len(self.labels),
                note="Inference will still work but labels may be misaligned",
            )

    def predict(self, image: Image.Image) -> DiseasePredictionResult:
        """Run inference on a single image.

        Args:
            image: PIL.Image in RGB mode.

        Returns:
            DiseasePredictionResult with top prediction and full distribution.

        Raises:
            ValueError: if image is invalid or preprocessing fails.
        """
        start_time = time.perf_counter()

        # --- Preprocess ---
        input_tensor = self.preprocess(image)

        # --- Inference ---
        outputs = self.session.run(None, {self.input_name: input_tensor})
        logits = outputs[0]  # Shape: (1, num_classes)

        # --- Postprocess ---
        all_predictions = self.postprocess(logits)

        inference_time_ms = (time.perf_counter() - start_time) * 1000

        top = all_predictions[0]
        is_reliable = top.confidence >= MIN_CONFIDENCE_THRESHOLD

        return DiseasePredictionResult(
            top_prediction=top,
            all_predictions=all_predictions,
            model_name="disease_classifier",
            model_version=self.model_version,
            inference_time_ms=inference_time_ms,
            is_reliable=is_reliable,
        )

    def preprocess(self, image: Image.Image) -> np.ndarray:
        """Preprocess a PIL image for YOLOv8 inference.

        Steps:
        1. Convert to RGB (in case of grayscale or RGBA input)
        2. Resize to 640x640 with letterbox padding (preserve aspect ratio)
        3. Convert to float32 and normalize to [0, 1]
        4. Apply ImageNet mean/std normalization
        5. Convert HWC -> CHW (channel-first)
        6. Add batch dimension -> NCHW

        Args:
            image: PIL.Image (any mode).

        Returns:
            np.ndarray of shape (1, 3, 640, 640), dtype float32.
        """
        if image is None:
            raise ValueError("Image is None")

        # 1. Convert to RGB
        if image.mode != "RGB":
            image = image.convert("RGB")

        # 2. Resize with letterbox padding
        image_resized = self._letterbox_resize(image, INPUT_SIZE, INPUT_SIZE)

        # 3. Convert to numpy and normalize to [0, 1]
        img_array = np.asarray(image_resized, dtype=np.float32) / 255.0

        # 4. Apply ImageNet normalization
        img_array = (img_array - IMAGENET_MEAN) / IMAGENET_STD

        # 5. HWC -> CHW
        img_array = np.transpose(img_array, (2, 0, 1))

        # 6. Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)

        # Ensure contiguous memory layout (ONNX Runtime requirement)
        return np.ascontiguousarray(img_array)

    def postprocess(
        self, logits: np.ndarray, top_k: int = 5
    ) -> list[Prediction]:
        """Convert raw logits to calibrated prediction list.

        Steps:
        1. Apply temperature scaling for calibration
        2. Compute softmax probabilities
        3. Sort by probability (descending)
        4. Take top-k predictions
        5. Map class indices to label strings

        Args:
            logits: np.ndarray of shape (1, num_classes) or (num_classes,).
            top_k: Number of top predictions to return.

        Returns:
            List of Prediction objects, sorted by confidence (descending).
        """
        # Squeeze batch dimension if present
        if logits.ndim == 2:
            logits = logits[0]  # (num_classes,)

        # 1. Temperature scaling
        scaled_logits = logits / TEMPERATURE

        # 2. Softmax with numerical stability
        shifted = scaled_logits - np.max(scaled_logits)
        exp_scores = np.exp(shifted)
        probabilities = exp_scores / np.sum(exp_scores)

        # 3. Sort descending
        sorted_indices = np.argsort(probabilities)[::-1]

        # 4. Top-k
        top_k = min(top_k, len(sorted_indices))
        top_indices = sorted_indices[:top_k]

        # 5. Map to labels
        predictions: list[Prediction] = []
        for idx in top_indices:
            label = self.labels[idx] if idx < len(self.labels) else f"unknown_{idx}"
            confidence = float(probabilities[idx])
            # Convert label to disease slug (lowercase, underscores)
            disease_slug = label.lower().replace(" ", "_").replace("-", "_")
            predictions.append(
                Prediction(
                    label=label,
                    confidence=confidence,
                    disease_slug=disease_slug,
                )
            )

        return predictions

    def _letterbox_resize(
        self, image: Image.Image, target_w: int, target_h: int
    ) -> Image.Image:
        """Resize image preserving aspect ratio, with letterbox padding.

        The image is scaled to fit within (target_w, target_h) while preserving
        aspect ratio, then padded with gray (128, 128, 128) to fill the target
        size. This is the standard YOLO preprocessing approach.
        """
        orig_w, orig_h = image.size
        scale = min(target_w / orig_w, target_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        # Resize with high-quality Lanczos resampling
        resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Create padded canvas
        canvas = Image.new("RGB", (target_w, target_h), (128, 128, 128))

        # Center the resized image on the canvas
        paste_x = (target_w - new_w) // 2
        paste_y = (target_h - new_h) // 2
        canvas.paste(resized, (paste_x, paste_y))

        return canvas


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_classifier: DiseaseClassifier | None = None


def get_disease_classifier() -> DiseaseClassifier:
    """Get the singleton DiseaseClassifier instance.

    Loads the ONNX model on first access (lazy initialization).
    """
    global _classifier
    if _classifier is None:
        loader = get_model_loader()
        session = loader.get_session("disease_classifier")
        _classifier = DiseaseClassifier(session)
    return _classifier
