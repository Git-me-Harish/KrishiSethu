"""Model evaluation script for crop disease classifier.

Evaluates a trained YOLOv8 model on the test set and produces:
- Top-1 and Top-5 accuracy
- Per-class precision, recall, F1-score
- Confusion matrix
- Classification report (saved as JSON + printed)

Usage:
    python -m ml.evaluation.evaluate_disease_classifier \
        --model-path ./models/disease_classifier_v1/best.pt \
        --data-path ./data/processed \
        --output-path ./evaluation_results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

try:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        top_k_accuracy_score,
    )
except ImportError:
    print("ERROR: scikit-learn not installed. Run: pip install scikit-learn")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_model(
    model_path: str,
    data_path: str,
    output_path: str = "./evaluation_results",
    img_size: int = 640,
    batch_size: int = 32,
    device: int | str = 0,
) -> dict[str, Any]:
    """Evaluate a trained model on the test set.

    Args:
        model_path: Path to best.pt model weights
        data_path: Path to processed dataset (must contain test/ directory)
        output_path: Where to save evaluation results
        img_size: Image size for inference
        batch_size: Batch size for inference
        device: GPU index or "cpu"

    Returns:
        Evaluation results dict
    """
    print("=" * 70)
    print("KrishiSetu — Disease Classifier Evaluation")
    print("=" * 70)
    print(f"Model: {model_path}")
    print(f"Data: {data_path}")
    print(f"Image size: {img_size}")
    print("=" * 70)

    # Verify paths
    model_file = Path(model_path)
    if not model_file.exists():
        print(f"ERROR: Model file not found: {model_file}")
        sys.exit(1)

    test_dir = Path(data_path) / "test"
    if not test_dir.exists():
        print(f"ERROR: Test directory not found: {test_dir}")
        sys.exit(1)

    # Get class names from directory structure
    class_names = sorted([
        d.name for d in test_dir.iterdir() if d.is_dir()
    ])
    print(f"Classes: {len(class_names)}")

    # Load model
    print("\nLoading model...")
    model = YOLO(str(model_file))

    # Run validation on test set
    print("\nRunning evaluation on test set...")
    results = model.val(
        data=str(data_path),
        split="test",
        imgsz=img_size,
        batch=batch_size,
        device=device,
        verbose=True,
    )

    # Extract metrics
    top1_accuracy = results.top1 if hasattr(results, "top1") else None
    top5_accuracy = results.top5 if hasattr(results, "top5") else None

    print(f"\n{'=' * 70}")
    print("Evaluation Results")
    print(f"{'=' * 70}")
    print(f"Top-1 Accuracy: {top1_accuracy:.4f}" if top1_accuracy else "Top-1: N/A")
    print(f"Top-5 Accuracy: {top5_accuracy:.4f}" if top5_accuracy else "Top-5: N/A")

    # Collect predictions for detailed metrics
    print("\nCollecting predictions for detailed analysis...")
    y_true = []
    y_pred = []
    y_pred_top5 = []

    for class_idx, class_name in enumerate(class_names):
        class_dir = test_dir / class_name
        for img_file in class_dir.iterdir():
            if img_file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue

            result = model.predict(
                source=str(img_file),
                imgsz=img_size,
                device=device,
                verbose=False,
            )

            if result and len(result) > 0:
                probs = result[0].probs
                if probs is not None:
                    y_true.append(class_idx)
                    y_pred.append(probs.top1)
                    # Top-5 predictions
                    top5 = probs.top5 if hasattr(probs, "top5") else [probs.top1]
                    y_pred_top5.append(top5)

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)

    # Compute metrics
    accuracy = accuracy_score(y_true, y_pred)

    # Top-5 accuracy
    top5_acc = 0.0
    if y_pred_top5:
        correct = sum(1 for true, pred5 in zip(y_true, y_pred_top5) if true in pred5)
        top5_acc = correct / len(y_true)

    # Per-class report
    report = classification_report(
        y_true, y_pred,
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)

    # Save results
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    eval_results = {
        "model_path": str(model_file),
        "data_path": str(data_path),
        "num_classes": len(class_names),
        "class_names": class_names,
        "total_test_images": len(y_true),
        "top1_accuracy": float(accuracy),
        "top5_accuracy": float(top5_acc),
        "per_class_report": report,
        "confusion_matrix": cm.tolist(),
        "image_size": img_size,
    }

    # Save JSON
    with open(output_dir / "evaluation_results.json", "w") as f:
        json.dump(eval_results, f, indent=2)

    # Print summary
    print(f"\n{'=' * 70}")
    print("Detailed Results")
    print(f"{'=' * 70}")
    print(f"Top-1 Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"Top-5 Accuracy: {top5_acc:.4f} ({top5_acc*100:.2f}%)")
    print(f"\nPer-Class Report:")
    print(f"{'Class':<40} {'Precision':<12} {'Recall':<12} {'F1':<12} {'Support'}")
    print("-" * 90)
    for class_name in class_names:
        if class_name in report:
            r = report[class_name]
            print(f"{class_name:<40} {r['precision']:<12.4f} {r['recall']:<12.4f} {r['f1-score']:<12.4f} {r['support']}")
    print("-" * 90)
    print(f"{'Macro Avg':<40} {report['macro avg']['precision']:<12.4f} {report['macro avg']['recall']:<12.4f} {report['macro avg']['f1-score']:<12.4f} {report['macro avg']['support']}")
    print(f"{'Weighted Avg':<40} {report['weighted avg']['precision']:<12.4f} {report['weighted avg']['recall']:<12.4f} {report['weighted avg']['f1-score']:<12.4f} {report['weighted avg']['support']}")

    # Check thresholds
    print(f"\n{'=' * 70}")
    print("Threshold Check")
    print(f"{'=' * 70}")
    checks = [
        ("Top-1 Accuracy ≥ 92%", accuracy >= 0.92),
        ("Top-5 Accuracy ≥ 98%", top5_acc >= 0.98),
        ("Macro-F1 ≥ 0.88", report["macro avg"]["f1-score"] >= 0.88),
        ("No class with F1 < 0.75", all(
            report[cn]["f1-score"] >= 0.75 for cn in class_names
            if cn in report and report[cn]["support"] > 0
        )),
    ]
    for desc, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")

    print(f"\nResults saved to: {output_dir / 'evaluation_results.json'}")
    return eval_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate crop disease classifier"
    )
    parser.add_argument("--model-path", type=str, required=True,
                        help="Path to best.pt model weights")
    parser.add_argument("--data-path", type=str, required=True,
                        help="Path to processed dataset")
    parser.add_argument("--output-path", type=str, default="./evaluation_results",
                        help="Where to save evaluation results")
    parser.add_argument("--img-size", type=int, default=640)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", type=str, default="0")
    args = parser.parse_args()

    evaluate_model(
        model_path=args.model_path,
        data_path=args.data_path,
        output_path=args.output_path,
        img_size=args.img_size,
        batch_size=args.batch_size,
        device=args.device if args.device == "cpu" else int(args.device),
    )
