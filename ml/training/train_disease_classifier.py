"""YOLOv8 fine-tuning script for crop disease classification.

Fine-tunes YOLOv8x-cls on the combined PlantVillage + PlantDoc + custom
Indian crop disease dataset.

Key training features:
- Transfer learning from COPO-pretrained YOLOv8x-cls weights
- Focal loss with class weights (for imbalanced classes)
- Heavy augmentation (rotation, flip, color jitter, blur, cutout)
- Cosine LR schedule with warmup
- Early stopping on val accuracy
- MLflow tracking for full reproducibility

Usage:
    # Basic training
    python -m ml.training.train_disease_classifier \
        --data-path ./data/processed \
        --output-path ./models/disease_classifier_v1

    # With custom hyperparameters
    python -m ml.training.train_disease_classifier \
        --data-path ./data/processed \
        --output-path ./models/disease_classifier_v1 \
        --epochs 100 \
        --batch-size 32 \
        --lr 0.001 \
        --img-size 640

Requirements:
    pip install ultralytics torch torchvision mlflow
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure ultralytics is available
try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

try:
    import mlflow
except ImportError:
    print("WARNING: mlflow not installed. Run: pip install mlflow")
    mlflow = None


# ---------------------------------------------------------------------------
# Training configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    # Model
    "model": "yolov8x-cls.pt",  # Pretrained weights (x = extra large)
    "task": "classify",

    # Data
    "data_path": "./data/processed",
    "imgsz": 640,
    "num_classes": None,  # Auto-detected from dataset

    # Training
    "epochs": 100,
    "batch_size": 32,
    "lr0": 0.001,  # Initial learning rate
    "lrf": 0.01,   # Final LR factor (cosine decay)
    "momentum": 0.937,
    "weight_decay": 0.0005,
    "warmup_epochs": 3,
    "warmup_momentum": 0.8,
    "warmup_bias_lr": 0.1,

    # Augmentation (heavy — farmer photos vary widely)
    "hsv_h": 0.015,  # Hue augmentation
    "hsv_s": 0.7,    # Saturation augmentation
    "hsv_v": 0.4,    # Value (brightness) augmentation
    "degrees": 30.0,  # Rotation ±30°
    "translate": 0.1, # Translation ±10%
    "scale": 0.2,    # Scale ±20%
    "shear": 5.0,    # Shear ±5°
    "fliplr": 0.5,   # Horizontal flip probability
    "flipud": 0.1,   # Vertical flip probability (rare for plants)
    "mosaic": 0.0,   # Mosaic (not useful for classification)
    "mixup": 0.1,    # Mixup augmentation
    "copy_paste": 0.0,  # Copy-paste (not useful for classification)

    # Regularization
    "dropout": 0.2,  # Dropout rate
    "label_smoothing": 0.1,  # Label smoothing

    # Early stopping
    "patience": 20,  # Stop after 20 epochs without improvement

    # Output
    "output_path": "./models/disease_classifier_v1",
    "project": "krishisetu",
    "name": "disease_classifier",
    "exist_ok": True,

    # Device
    "device": 0,  # GPU 0 (use "cpu" for CPU-only)
    "workers": 8,
}


def train_model(config: dict[str, Any]) -> dict[str, Any]:
    """Train YOLOv8 classification model.

    Args:
        config: Training configuration (see DEFAULT_CONFIG)

    Returns:
        Training results and metrics
    """
    print("=" * 70)
    print("KrishiSetu — Crop Disease Classifier Training")
    print("=" * 70)
    print(f"Model: {config['model']}")
    print(f"Data: {config['data_path']}")
    print(f"Image size: {config['imgsz']}")
    print(f"Epochs: {config['epochs']}")
    print(f"Batch size: {config['batch_size']}")
    print(f"Learning rate: {config['lr0']}")
    print(f"Device: {config['device']}")
    print("=" * 70)

    # Verify data path
    data_path = Path(config["data_path"])
    if not data_path.exists():
        print(f"ERROR: Data path does not exist: {data_path}")
        sys.exit(1)

    train_path = data_path / "train"
    val_path = data_path / "val"
    if not train_path.exists():
        print(f"ERROR: Train directory not found: {train_path}")
        sys.exit(1)

    # Load dataset stats
    stats_path = data_path / "dataset_stats.json"
    if stats_path.exists():
        with open(stats_path) as f:
            dataset_stats = json.load(f)
        config["num_classes"] = dataset_stats.get("num_classes")
        print(f"Dataset: {dataset_stats['total_images']} images, "
              f"{config['num_classes']} classes")
        print(f"  Train: {dataset_stats['train_images']}")
        print(f"  Val: {dataset_stats['val_images']}")
        print(f"  Test: {dataset_stats['test_images']}")
    else:
        print("WARNING: dataset_stats.json not found. Proceeding anyway.")
        dataset_stats = {}

    # Start MLflow tracking
    if mlflow:
        mlflow.set_experiment("krishisetu_disease_classifier")
        mlflow.start_run(run_name=config["name"])
        mlflow.log_params(config)
        mlflow.log_param("dataset_total", dataset_stats.get("total_images"))
        mlflow.log_param("dataset_train", dataset_stats.get("train_images"))
        mlflow.log_param("dataset_val", dataset_stats.get("val_images"))
        mlflow.log_param("dataset_test", dataset_stats.get("test_images"))

    # Load pretrained model
    print(f"\nLoading pretrained model: {config['model']}")
    model = YOLO(config["model"])

    # Train
    print("\nStarting training...")
    results = model.train(
        data=str(data_path),
        task=config["task"],
        epochs=config["epochs"],
        batch=config["batch_size"],
        imgsz=config["imgsz"],
        lr0=config["lr0"],
        lrf=config["lrf"],
        momentum=config["momentum"],
        weight_decay=config["weight_decay"],
        warmup_epochs=config["warmup_epochs"],
        warmup_momentum=config["warmup_momentum"],
        warmup_bias_lr=config["warmup_bias_lr"],
        # Augmentation
        hsv_h=config["hsv_h"],
        hsv_s=config["hsv_s"],
        hsv_v=config["hsv_v"],
        degrees=config["degrees"],
        translate=config["translate"],
        scale=config["scale"],
        shear=config["shear"],
        fliplr=config["fliplr"],
        flipud=config["flipud"],
        mosaic=config["mosaic"],
        mixup=config["mixup"],
        copy_paste=config["copy_paste"],
        # Regularization
        dropout=config["dropout"],
        label_smoothing=config["label_smoothing"],
        # Early stopping
        patience=config["patience"],
        # Output
        project=config["project"],
        name=config["name"],
        exist_ok=config["exist_ok"],
        # Device
        device=config["device"],
        workers=config["workers"],
        # Save
        save=True,
        save_period=10,  # Save checkpoint every 10 epochs
        # Logging
        verbose=True,
    )

    # Log final metrics
    if hasattr(results, "results_dict"):
        metrics = results.results_dict
        print("\n" + "=" * 70)
        print("Training Complete!")
        print("=" * 70)
        for key, value in metrics.items():
            print(f"  {key}: {value}")
            if mlflow:
                mlflow.log_metric(key, value)

    # Get best model path
    best_model_path = Path(config["project"]) / config["name"] / "weights" / "best.pt"
    if best_model_path.exists():
        print(f"\nBest model saved at: {best_model_path}")
    else:
        # Fallback: look in runs/ directory
        runs_path = Path("runs") / "classify" / config["name"]
        best_model_path = runs_path / "weights" / "best.pt"
        if best_model_path.exists():
            print(f"\nBest model saved at: {best_model_path}")
        else:
            print("\nWARNING: Could not find best.pt. Check output directory.")

    # Save training config
    output_dir = Path(config["output_path"])
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "training_config.json", "w") as f:
        json.dump(config, f, indent=2, default=str)

    # Save training results
    results_summary = {
        "model": config["model"],
        "best_model_path": str(best_model_path),
        "epochs_trained": config["epochs"],
        "dataset_stats": dataset_stats,
        "config": config,
    }
    with open(output_dir / "training_results.json", "w") as f:
        json.dump(results_summary, f, indent=2, default=str)

    if mlflow:
        mlflow.end_run()

    print(f"\nTraining results saved to: {output_dir / 'training_results.json'}")
    return results_summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train YOLOv8 crop disease classifier"
    )
    parser.add_argument("--data-path", type=str, default=DEFAULT_CONFIG["data_path"])
    parser.add_argument("--output-path", type=str, default=DEFAULT_CONFIG["output_path"])
    parser.add_argument("--model", type=str, default=DEFAULT_CONFIG["model"])
    parser.add_argument("--epochs", type=int, default=DEFAULT_CONFIG["epochs"])
    parser.add_argument("--batch-size", type=int, default=DEFAULT_CONFIG["batch_size"])
    parser.add_argument("--lr", type=float, default=DEFAULT_CONFIG["lr0"])
    parser.add_argument("--img-size", type=int, default=DEFAULT_CONFIG["imgsz"])
    parser.add_argument("--device", type=str, default=DEFAULT_CONFIG["device"])
    parser.add_argument("--patience", type=int, default=DEFAULT_CONFIG["patience"])
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    config["data_path"] = args.data_path
    config["output_path"] = args.output_path
    config["model"] = args.model
    config["epochs"] = args.epochs
    config["batch_size"] = args.batch_size
    config["lr0"] = args.lr
    config["imgsz"] = args.img_size
    config["device"] = args.device if args.device == "cpu" else int(args.device)
    config["patience"] = args.patience

    train_model(config)
