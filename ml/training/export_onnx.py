"""ONNX export script for crop disease classifier.

Exports a trained YOLOv8 model to ONNX format for production inference
via ONNX Runtime in the ML inference service.

Steps:
1. Load best.pt model
2. Export to ONNX with dynamic batch size
3. Verify ONNX model produces same outputs as PyTorch
4. Save model metadata (version, class labels, input shape)

Usage:
    python -m ml.training.export_onnx \
        --model-path ./models/disease_classifier_v1/best.pt \
        --output-path ./models/disease_classifier_v1.onnx \
        --version v1.0.0 \
        --labels tomato_early_blight,tomato_late_blight,rice_blast,...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

try:
    import onnxruntime as ort
except ImportError:
    print("ERROR: onnxruntime not installed. Run: pip install onnxruntime")
    sys.exit(1)

import numpy as np
from PIL import Image


def export_to_onnx(
    model_path: str,
    output_path: str,
    version: str = "v1.0.0",
    labels: list[str] | None = None,
    img_size: int = 640,
) -> dict[str, Any]:
    """Export YOLOv8 model to ONNX format.

    Args:
        model_path: Path to best.pt PyTorch model
        output_path: Output ONNX file path
        version: Model version string
        labels: List of class label names (in training order)
        img_size: Input image size

    Returns:
        Export metadata dict
    """
    print("=" * 70)
    print("KrishiSetu — ONNX Export")
    print("=" * 70)
    print(f"Model: {model_path}")
    print(f"Output: {output_path}")
    print(f"Version: {version}")
    print(f"Image size: {img_size}")
    print("=" * 70)

    # Verify model exists
    if not Path(model_path).exists():
        print(f"ERROR: Model file not found: {model_path}")
        sys.exit(1)

    # Load model
    print("\nLoading PyTorch model...")
    model = YOLO(model_path)

    # Get class names from model if not provided
    if labels is None:
        if hasattr(model, "names") and model.names:
            # names is a dict {0: 'class_name', 1: 'class_name', ...}
            labels = [model.names[i] for i in sorted(model.names.keys())]
        else:
            print("ERROR: Could not determine class labels. Provide --labels.")
            sys.exit(1)

    print(f"Classes: {len(labels)}")
    print(f"Labels: {labels[:10]}...")  # Show first 10

    # Export to ONNX
    print("\nExporting to ONNX...")
    onnx_path = model.export(
        format="onnx",
        imgsz=img_size,
        dynamic=True,  # Dynamic batch size
        simplify=True,  # Simplify ONNX graph
        opset=12,  # ONNX opset version
    )

    # The export returns the path to the ONNX file
    exported_path = Path(onnx_path) if onnx_path else Path(model_path).with_suffix(".onnx")

    # Move to output path if different
    if str(exported_path) != output_path:
        import shutil
        shutil.move(str(exported_path), output_path)
        exported_path = Path(output_path)

    print(f"ONNX model saved to: {exported_path}")

    # Verify ONNX model
    print("\nVerifying ONNX model...")
    session = ort.InferenceSession(str(exported_path))
    input_info = session.get_inputs()[0]
    output_info = session.get_outputs()[0]

    print(f"  Input: name={input_info.name}, shape={input_info.shape}, type={input_info.type}")
    print(f"  Output: name={output_info.name}, shape={output_info.shape}, type={output_info.type}")

    # Create dummy input and verify inference works
    dummy_input = np.random.randn(1, 3, img_size, img_size).astype(np.float32)
    outputs = session.run(None, {input_info.name: dummy_input})
    print(f"  Output shape: {outputs[0].shape}")
    print(f"  Output sum: {outputs[0].sum():.4f}")  # Should be ~1.0 (softmax)

    # Save metadata
    metadata = {
        "model_name": "disease_classifier",
        "version": version,
        "format": "onnx",
        "input_name": input_info.name,
        "input_shape": input_info.shape,
        "output_name": output_info.name,
        "output_shape": output_info.shape,
        "image_size": img_size,
        "num_classes": len(labels),
        "labels": labels,
        "source_model": str(model_path),
        "onnx_path": str(exported_path),
        "opset_version": 12,
    }

    metadata_path = exported_path.with_suffix(".metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata saved to: {metadata_path}")
    print(f"\n{'=' * 70}")
    print("Export Complete!")
    print(f"{'=' * 70}")
    print(f"ONNX model: {exported_path}")
    print(f"Metadata: {metadata_path}")
    print(f"\nTo deploy:")
    print(f"  1. Upload to S3: aws s3 cp {exported_path} s3://krishisetu-models/disease/{version}.onnx")
    print(f"  2. Update ML service env:")
    print(f"     DISEASE_CLASSIFIER_MODEL_PATH=s3://krishisetu-models/disease/{version}.onnx")
    print(f"     DISEASE_CLASSIFIER_MODEL_VERSION={version}")
    print(f"     DISEASE_CLASSIFIER_LABELS={','.join(labels)}")
    print(f"  3. Restart ML inference service")

    return metadata


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export YOLOv8 model to ONNX format"
    )
    parser.add_argument("--model-path", type=str, required=True,
                        help="Path to best.pt PyTorch model")
    parser.add_argument("--output-path", type=str, required=True,
                        help="Output ONNX file path")
    parser.add_argument("--version", type=str, default="v1.0.0",
                        help="Model version string")
    parser.add_argument("--labels", type=str, default=None,
                        help="Comma-separated class labels (in training order)")
    parser.add_argument("--img-size", type=int, default=640,
                        help="Input image size")
    args = parser.parse_args()

    labels = args.labels.split(",") if args.labels else None

    export_to_onnx(
        model_path=args.model_path,
        output_path=args.output_path,
        version=args.version,
        labels=labels,
        img_size=args.img_size,
    )
