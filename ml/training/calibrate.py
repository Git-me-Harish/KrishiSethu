"""Temperature scaling calibration for confidence calibration.

After training, the model's softmax outputs may not be well-calibrated —
a prediction with 90% confidence may only be correct 80% of the time.

Temperature scaling fixes this by dividing the logits by a learned
temperature parameter T:
    calibrated_probs = softmax(logits / T)

T is optimized on the validation set to minimize NLL loss.

A well-calibrated model is critical for our use case because we use
confidence thresholds (70%) to decide whether to route to officer review.

Usage:
    python -m ml.training.calibrate \
        --model-path ./models/disease_classifier_v1/best.pt \
        --data-path ./data/processed \
        --output-path ./models/disease_classifier_v1/calibration.json
"""

from __future__ import annotations

import argparse
import json
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
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError:
    print("ERROR: torch not installed. Run: pip install torch")
    sys.exit(1)

try:
    from sklearn.metrics import log_loss
except ImportError:
    print("ERROR: scikit-learn not installed. Run: pip install scikit-learn")
    sys.exit(1)


class TemperatureScaler:
    """Learn a temperature parameter for confidence calibration.

    The temperature T is a single scalar that divides all logits:
        calibrated_logits = logits / T

    T > 1 makes the model less confident (softer probabilities)
    T < 1 makes the model more confident (sharper probabilities)
    """

    def __init__(self) -> None:
        self.temperature = nn.Parameter(torch.ones(1) * 1.5)

    def fit(self, logits: np.ndarray, labels: np.ndarray, max_iter: int = 100) -> float:
        """Fit temperature on validation logits and labels.

        Args:
            logits: Model logits (before softmax), shape (N, C)
            labels: True class indices, shape (N,)
            max_iter: Maximum optimization iterations

        Returns:
            Optimal temperature value
        """
        logits_tensor = torch.from_numpy(logits).float()
        labels_tensor = torch.from_numpy(labels).long()

        optimizer = torch.optim.LBFGS(
            [self.temperature], lr=0.01, max_iter=max_iter
        )

        def closure():
            optimizer.zero_grad()
            scaled_logits = logits_tensor / self.temperature
            loss = F.cross_entropy(scaled_logits, labels_tensor)
            loss.backward()
            return loss

        optimizer.step(closure)

        temp_value = self.temperature.item()
        return temp_value

    def calibrate(self, logits: np.ndarray) -> np.ndarray:
        """Apply temperature scaling to logits.

        Returns calibrated softmax probabilities.
        """
        logits_tensor = torch.from_numpy(logits).float()
        scaled_logits = logits_tensor / self.temperature
        return F.softmax(scaled_logits, dim=1).numpy()


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """Compute Expected Calibration Error (ECE).

    ECE measures the difference between predicted confidence and actual accuracy
    across confidence bins. Lower is better (0 = perfectly calibrated).

    Args:
        probs: Predicted probabilities (max prob per sample), shape (N,)
        labels: True labels (binary: correct/incorrect), shape (N,)
        n_bins: Number of confidence bins

    Returns:
        ECE score
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(labels)

    for i in range(n_bins):
        lower = bin_boundaries[i]
        upper = bin_boundaries[i + 1]
        mask = (probs > lower) & (probs <= upper)
        if mask.sum() == 0:
            continue
        bin_confidence = probs[mask].mean()
        bin_accuracy = labels[mask].mean()
        ece += (mask.sum() / n) * abs(bin_confidence - bin_accuracy)

    return ece


def calibrate_model(
    model_path: str,
    data_path: str,
    output_path: str = "./calibration.json",
    img_size: int = 640,
    device: int | str = 0,
) -> dict[str, Any]:
    """Calibrate model confidence using temperature scaling.

    Args:
        model_path: Path to best.pt model
        data_path: Path to processed dataset (must contain val/ directory)
        output_path: Where to save calibration results
        img_size: Image size for inference
        device: GPU index or "cpu"

    Returns:
        Calibration results dict
    """
    print("=" * 70)
    print("KrishiSetu — Confidence Calibration (Temperature Scaling)")
    print("=" * 70)

    # Load model
    print("Loading model...")
    model = YOLO(model_path)

    # Collect logits and labels from validation set
    val_dir = Path(data_path) / "val"
    if not val_dir.exists():
        print(f"ERROR: Validation directory not found: {val_dir}")
        sys.exit(1)

    class_names = sorted([d.name for d in val_dir.iterdir() if d.is_dir()])
    print(f"Classes: {len(class_names)}")

    all_logits = []
    all_labels = []

    print("Collecting predictions on validation set...")
    for class_idx, class_name in enumerate(class_names):
        class_dir = val_dir / class_name
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
                    # Get logits (inverse of softmax is log)
                    prob_array = probs.data.cpu().numpy()
                    logits = np.log(prob_array + 1e-8)  # Convert probs back to logits
                    all_logits.append(logits)
                    all_labels.append(class_idx)

    all_logits = np.array(all_logits)
    all_labels = np.array(all_labels)

    print(f"Collected {len(all_labels)} validation predictions")

    # Compute pre-calibration metrics
    pre_probs = np.exp(all_logits) / np.exp(all_logits).sum(axis=1, keepdims=True)
    pre_max_probs = pre_probs.max(axis=1)
    pre_correct = (pre_probs.argmax(axis=1) == all_labels).astype(float)
    pre_ece = compute_ece(pre_max_probs, pre_correct)

    print(f"\nPre-calibration:")
    print(f"  Accuracy: {pre_correct.mean():.4f}")
    print(f"  Mean confidence: {pre_max_probs.mean():.4f}")
    print(f"  ECE: {pre_ece:.4f}")

    # Fit temperature
    print("\nFitting temperature parameter...")
    scaler = TemperatureScaler()
    optimal_temp = scaler.fit(all_logits, all_labels)

    # Compute post-calibration metrics
    calibrated_probs = scaler.calibrate(all_logits)
    cal_max_probs = calibrated_probs.max(axis=1)
    cal_correct = (calibrated_probs.argmax(axis=1) == all_labels).astype(float)
    cal_ece = compute_ece(cal_max_probs, cal_correct)

    print(f"\nPost-calibration:")
    print(f"  Temperature: {optimal_temp:.4f}")
    print(f"  Accuracy: {cal_correct.mean():.4f} (unchanged)")
    print(f"  Mean confidence: {cal_max_probs.mean():.4f}")
    print(f"  ECE: {cal_ece:.4f}")

    # Check threshold
    print(f"\n{'=' * 70}")
    print("Calibration Check")
    print(f"{'=' * 70}")
    checks = [
        ("ECE ≤ 0.05", cal_ece <= 0.05),
        ("Temperature in [0.5, 3.0]", 0.5 <= optimal_temp <= 3.0),
        ("Mean confidence ≈ accuracy", abs(cal_max_probs.mean() - cal_correct.mean()) < 0.05),
    ]
    for desc, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {desc}")

    # Save results
    results = {
        "model_path": str(model_path),
        "temperature": float(optimal_temp),
        "pre_calibration_ece": float(pre_ece),
        "post_calibration_ece": float(cal_ece),
        "pre_calibration_mean_confidence": float(pre_max_probs.mean()),
        "post_calibration_mean_confidence": float(cal_max_probs.mean()),
        "accuracy": float(cal_correct.mean()),
        "num_validation_samples": len(all_labels),
        "num_classes": len(class_names),
        "class_names": class_names,
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nCalibration results saved to: {output_file}")
    print(f"\nTo use in ML inference service:")
    print(f"  Set TEMPERATURE={optimal_temp:.4f} in apps/ml-inference/.env")
    print(f"  Or update krishisetu_ml/models/disease_classifier.py TEMPERATURE constant")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Calibrate model confidence using temperature scaling"
    )
    parser.add_argument("--model-path", type=str, required=True,
                        help="Path to best.pt model")
    parser.add_argument("--data-path", type=str, required=True,
                        help="Path to processed dataset")
    parser.add_argument("--output-path", type=str, default="./calibration.json",
                        help="Output path for calibration results")
    parser.add_argument("--img-size", type=int, default=640)
    parser.add_argument("--device", type=str, default="0")
    args = parser.parse_args()

    calibrate_model(
        model_path=args.model_path,
        data_path=args.data_path,
        output_path=args.output_path,
        img_size=args.img_size,
        device=args.device if args.device == "cpu" else int(args.device),
    )
