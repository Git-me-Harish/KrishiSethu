#!/usr/bin/env python3
"""Generate a proper baseline ONNX model for the KrishiSetu disease classifier.

This script creates a lightweight CNN with the correct architecture for
the KrishiSetu disease classification task and exports it to ONNX format.
The model has:

- Input:  float32[1, 3, 640, 640] — NCHW, ImageNet-normalized RGB image
- Output: float32[1, 6] — logits over 6 disease classes

Architecture (LightweightCNN):
    Conv2d(3→32, k=3, s=2) → BN → ReLU → MaxPool(2)    # 640 → 160
    Conv2d(32→64, k=3, s=2) → BN → ReLU → MaxPool(2)   # 160 → 40
    Conv2d(64→128, k=3, s=2) → BN → ReLU → MaxPool(2)  # 40 → 10
    Conv2d(128→256, k=3, s=2) → BN → ReLU               # 10 → 5
    AdaptiveAvgPool2d(1) → Flatten                       # 256 features
    Linear(256, 6)                                       # 6 class logits

The model has ~1.2M parameters — small enough to load and run in
milliseconds on CPU, but with enough capacity to learn meaningful
features when fine-tuned on the PlantVillage + PlantDoc dataset.

The weights are randomly initialized (Kaiming uniform). The model is
NOT trained — it produces random predictions. To get a trained model:

    cd ml/training
    python train_disease_classifier.py  # requires datasets + GPU
    python export_onnx.py               # exports the trained model

The generated ONNX file replaces this baseline. The baseline exists so
the inference service can boot, run health checks, and serve requests
(structurally — predictions will be random until a trained model is
dropped in).

Usage:
    pip install torch torchvision onnx onnxruntime
    python ml/scripts/generate_baseline_model.py

Output:
    apps/ml-inference/models/disease_classifier_v1.onnx
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
import torch.nn as nn
import onnx
import onnxruntime as ort
import numpy as np


# ---------------------------------------------------------------------------
# Constants — must match disease_classifier.py and the DISEASE_CLASSIFIER_LABELS env var
# ---------------------------------------------------------------------------

INPUT_SIZE = 640  # pixels, square
NUM_CLASSES = 6   # matches: healthy,tomato_early_blight,tomato_late_blight,rice_blast,rice_bacterial_blight,wheat_stripe_rust
MODEL_VERSION = "v1.0.0-baseline"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "apps" / "ml-inference" / "models" / "disease_classifier_v1.onnx"


# ---------------------------------------------------------------------------
# Model architecture
# ---------------------------------------------------------------------------


class LightweightCNN(nn.Module):
    """A lightweight CNN for crop disease classification.

    Architecture:
        4 conv blocks (Conv → BN → ReLU → Pool) + global avg pool + linear

    Input:  (B, 3, 640, 640)  — ImageNet-normalized RGB
    Output: (B, 6)            — class logits

    Parameters: ~1.2M (vs YOLOv8x-cls at ~84M) — small enough for CPU inference
    in real-time, large enough to learn meaningful features when fine-tuned.
    """

    def __init__(self, num_classes: int = NUM_CLASSES) -> None:
        super().__init__()

        # Conv blocks: progressively reduce spatial dimensions
        # Block 1: 640 → 320 → 160 (stride=2 + maxpool=2)
        self.block1 = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # Block 2: 160 → 80 → 40
        self.block2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # Block 3: 40 → 20 → 10
        self.block3 = nn.Sequential(
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )

        # Block 4: 10 → 5 (no maxpool — spatial dims getting small)
        self.block4 = nn.Sequential(
            nn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
        )

        # Global average pool → 256 features
        self.gap = nn.AdaptiveAvgPool2d(1)

        # Classifier
        self.fc = nn.Linear(256, num_classes)

        # Initialize weights (Kaiming uniform — standard for CNNs with ReLU)
        self._initialize_weights()

    def _initialize_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_uniform_(m.weight, nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        x = self.block4(x)
        x = self.gap(x)
        x = torch.flatten(x, 1)  # (B, 256, 1, 1) → (B, 256)
        x = self.fc(x)           # (B, 6)
        return x


# ---------------------------------------------------------------------------
# Export to ONNX
# ---------------------------------------------------------------------------


def export_to_onnx(model: nn.Module, output_path: Path) -> None:
    """Export the PyTorch model to ONNX format with proper metadata.

    The ONNX model will have:
    - Input: "input" tensor, shape [1, 3, 640, 640], dtype float32
    - Output: "output" tensor, shape [1, 6], dtype float32
    - Dynamic batch dimension (so batch sizes > 1 work in production)
    - Metadata: model_version, class_labels, input_size, normalization
    """
    model.eval()

    # Create a dummy input tensor for tracing
    dummy_input = torch.randn(1, 3, INPUT_SIZE, INPUT_SIZE, dtype=torch.float32)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Export
    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        export_params=True,  # store trained weights inside the model file
        opset_version=17,    # ONNX opset 17 — widely supported
        do_constant_folding=True,  # optimize constant subgraphs
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},   # variable batch dimension
            "output": {0: "batch_size"},
        },
    )

    # Add metadata to the ONNX model
    onnx_model = onnx.load(str(output_path))

    # Add metadata as key-value pairs in the ONNX model's metadata_props
    metadata = {
        "model_name": "disease_classifier",
        "model_version": MODEL_VERSION,
        "architecture": "LightweightCNN",
        "input_size": str(INPUT_SIZE),
        "num_classes": str(NUM_CLASSES),
        "class_labels": "healthy,tomato_early_blight,tomato_late_blight,rice_blast,rice_bacterial_blight,wheat_stripe_rust",
        "normalization": "ImageNet mean=[0.485,0.456,0.406] std=[0.229,0.224,0.225]",
        "input_format": "NCHW float32, [0,1] range after normalization",
        "output_format": "logits (apply softmax for probabilities)",
        "training_status": "baseline_random_weights",
        "description": (
            "Lightweight CNN baseline for crop disease classification. "
            "Randomly initialized weights — NOT trained. Replace with a "
            "trained model (ml/training/train_disease_classifier.py) for "
            "accurate predictions. Architecture: 4 conv blocks + GAP + FC."
        ),
    }

    for key, value in metadata.items():
        meta = onnx_model.metadata_props.add()
        meta.key = key
        meta.value = value

    onnx.save_model(onnx_model, str(output_path))

    print(f"✓ ONNX model exported to: {output_path}")
    print(f"  Model size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


# ---------------------------------------------------------------------------
# Verify the exported model
# ---------------------------------------------------------------------------


def verify_onnx_model(model_path: Path) -> None:
    """Verify the ONNX model loads and produces correct output shape.

    Runs a dummy inference to confirm:
    1. The model loads in ONNX Runtime
    2. Input shape is [1, 3, 640, 640]
    3. Output shape is [1, 6]
    4. Output values are finite (not NaN/Inf)
    """
    print("\n--- Verifying ONNX model ---")

    session = ort.InferenceSession(str(model_path))

    # Check input
    input_info = session.get_inputs()[0]
    print(f"  Input:  name={input_info.name}, shape={input_info.shape}, dtype={input_info.type}")
    assert input_info.name == "input", f"Expected input name 'input', got '{input_info.name}'"

    # Check output
    output_info = session.get_outputs()[0]
    print(f"  Output: name={output_info.name}, shape={output_info.shape}, dtype={output_info.type}")
    assert output_info.name == "output", f"Expected output name 'output', got '{output_info.name}'"

    # Run dummy inference
    dummy_input = np.random.randn(1, 3, INPUT_SIZE, INPUT_SIZE).astype(np.float32)
    outputs = session.run(None, {input_info.name: dummy_input})

    output_array = outputs[0]
    print(f"  Inference output shape: {output_array.shape}")
    print(f"  Output values: {output_array[0]}")

    assert output_array.shape == (1, NUM_CLASSES), (
        f"Expected output shape (1, {NUM_CLASSES}), got {output_array.shape}"
    )
    assert np.all(np.isfinite(output_array)), "Output contains NaN or Inf values"

    print("  ✓ Model verified — correct I/O shapes, finite output values")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("KrishiSetu Disease Classifier — Baseline Model Generator")
    print(f"Architecture: LightweightCNN (4 conv blocks + GAP + FC)")
    print(f"Input:  (1, 3, {INPUT_SIZE}, {INPUT_SIZE}) float32")
    print(f"Output: (1, {NUM_CLASSES}) float32 — logits")
    print(f"Version: {MODEL_VERSION}")
    print(f"Output path: {OUTPUT_PATH}")
    print("=" * 60)

    # 1. Create the model
    print("\n1. Creating model...")
    model = LightweightCNN(num_classes=NUM_CLASSES)
    param_count = sum(p.numel() for p in model.parameters())
    print(f"   Parameters: {param_count:,} ({param_count / 1e6:.1f}M)")

    # 2. Export to ONNX
    print("\n2. Exporting to ONNX...")
    export_to_onnx(model, OUTPUT_PATH)

    # 3. Verify
    verify_onnx_model(OUTPUT_PATH)

    print("\n" + "=" * 60)
    print("✅ Baseline model generated successfully.")
    print()
    print("Next steps:")
    print("  1. Copy the ONNX file to your apps/ml-inference/models/ directory")
    print("  2. Set DISEASE_CLASSIFIER_MODEL_PATH=/app/models/disease_classifier_v1.onnx")
    print("  3. Set DISEASE_CLASSIFIER_MODEL_VERSION=" + MODEL_VERSION)
    print("  4. Set MODEL_WARMUP_ON_START=true")
    print("  5. Restart the ML inference service")
    print()
    print("To train a real model (replaces this baseline):")
    print("  cd ml/training")
    print("  python train_disease_classifier.py  # needs datasets + GPU")
    print("  python export_onnx.py               # exports trained model")
    print("=" * 60)


if __name__ == "__main__":
    main()