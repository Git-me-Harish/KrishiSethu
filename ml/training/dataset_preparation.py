"""Dataset preparation for crop disease classification.

Combines and preprocesses multiple datasets:
1. PlantVillage (54K images, 38 classes) — lab-controlled
2. PlantDoc (2.6K images, 27 classes) — field conditions
3. Custom Indian dataset (collected from ICAR/farmer submissions)

Produces a unified dataset with:
- Consistent class labeling (mapped to our disease catalog slugs)
- Train/val/test split (70/15/15, stratified by class)
- Augmentation config for training set

Usage:
    python -m ml.training.dataset_preparation \
        --plantvillage-path /data/PlantVillage \
        --plantdoc-path /data/PlantDoc \
        --custom-path /data/custom_indian \
        --output-path /data/processed

Datasets expected directory structure:
    PlantVillage/
        Color/
            Tomato___Early_blight/
                image1.jpg
                ...
            Tomato___Late_blight/
                ...
    PlantDoc/
        train/
            Apple Scandal Leaf/
                ...
    custom_indian/
        rice_blast/
            ...
        rice_brown_spot/
            ...
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from pathlib import Path
from typing import Any

# Set random seed for reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Class mapping: dataset folder name → our disease catalog slug
# ---------------------------------------------------------------------------

# PlantVillage class names → KrishiSetu disease slugs
PLANTVILLAGE_MAP: dict[str, str] = {
    # Tomato
    "Tomato___Early_blight": "tomato_early_blight",
    "Tomato___Late_blight": "tomato_late_blight",
    "Tomato___Leaf_Mold": "tomato_leaf_mold",
    "Tomato___Septoria_leaf_spot": "tomato_septoria_leaf_spot",
    "Tomato___Spider_mites Two-spotted_spider_mite": "tomato_spider_mites",
    "Tomato___Target_Spot": "tomato_target_spot",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "tomato_leaf_curl",
    "Tomato___Tomato_mosaic_virus": "tomato_mosaic_virus",
    "Tomato___Bacterial_spot": "tomato_bacterial_spot",
    "Tomato___healthy": "healthy_tomato",
    # Potato
    "Potato___Early_blight": "potato_early_blight",
    "Potato___Late_blight": "tomato_late_blight",  # Same pathogen
    "Potato___healthy": "healthy_potato",
    # Pepper
    "Pepper,_bell___Bacterial_spot": "pepper_bacterial_spot",
    "Pepper,_bell___healthy": "healthy_pepper",
    # Corn/Maize
    "Corn___Cercospora_leaf_spot Gray_leaf_spot": "maize_leaf_blight",
    "Corn___Common_rust": "maize_common_rust",
    "Corn___Northern_Leaf_Blight": "maize_leaf_blight",
    "Corn___healthy": "healthy_maize",
    # Apple
    "Apple___Apple_scab": "apple_scab",
    "Apple___Black_rot": "apple_black_rot",
    "Apple___Cedar_apple_rust": "apple_cedar_rust",
    "Apple___healthy": "healthy_apple",
    # Grape
    "Grape___Black_rot": "grape_black_rot",
    "Grape___Esca_(Black_Measles)": "grape_esca",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "grape_leaf_blight",
    "Grape___healthy": "healthy_grape",
    # Cherry
    "Cherry___Powdery_mildew": "cherry_powdery_mildew",
    "Cherry___healthy": "healthy_cherry",
    # Peach
    "Peach___Bacterial_spot": "peach_bacterial_spot",
    "Peach___healthy": "healthy_peach",
    # Strawberry
    "Strawberry___Leaf_scorch": "strawberry_leaf_scorch",
    "Strawberry___healthy": "healthy_strawberry",
    # Soybean
    "Soybean___healthy": "healthy_soybean",
    # Squash
    "Squash___Powdery_mildew": "squash_powdery_mildew",
    # Blueberry
    "Blueberry___healthy": "healthy_blueberry",
    # Orange
    "Orange___Haunglongbing_(Citrus_greening)": "orange_huanglongbing",
    # Raspberry
    "Raspberry___healthy": "healthy_raspberry",
}

# PlantDoc class names → our disease slugs (subset, as PlantDoc has fewer classes)
PLANTDOC_MAP: dict[str, str] = {
    "Tomato Early blight leaf": "tomato_early_blight",
    "Tomato Late blight leaf": "tomato_late_blight",
    "Tomato leaf bacterial spot": "tomato_bacterial_spot",
    "Tomato Septoria leaf spot": "tomato_septoria_leaf_spot",
    "Tomato Yellow Leaf Curl Virus": "tomato_leaf_curl",
    "Tomato mold leaf": "tomato_leaf_mold",
    "Tomato Two-spotted spider mite leaf": "tomato_spider_mites",
    "Potato leaf early blight": "potato_early_blight",
    "Potato leaf late blight": "tomato_late_blight",
    "Apple Scab Leaf": "apple_scab",
    "Apple leaf": "healthy_apple",
    "Corn leaf blight": "maize_leaf_blight",
    "Grape leaf black rot": "grape_black_rot",
    "Peach leaf": "healthy_peach",
    "Strawberry leaf": "healthy_strawberry",
}


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------


def prepare_dataset(
    plantvillage_path: str | None = None,
    plantdoc_path: str | None = None,
    custom_path: str | None = None,
    output_path: str = "./data/processed",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> dict[str, Any]:
    """Prepare unified dataset from multiple sources.

    Creates the following directory structure:
        output_path/
            train/
                tomato_early_blight/
                    img001.jpg
                    ...
                rice_blast/
                    ...
            val/
                ...
            test/
                ...
            class_mapping.json
            dataset_stats.json

    Returns dataset statistics dict.
    """
    output = Path(output_path)

    # Create output directories
    for split in ("train", "val", "test"):
        (output / split).mkdir(parents=True, exist_ok=True)

    # Collect all images with their class labels
    all_images: list[tuple[str, str, str]] = []  # (image_path, class_slug, source)

    # Process PlantVillage
    if plantvillage_path:
        pv_count = _process_plantvillage(plantvillage_path, all_images)
        print(f"PlantVillage: {pv_count} images collected")
    else:
        pv_count = 0
        print("PlantVillage: skipped (no path provided)")

    # Process PlantDoc
    if plantdoc_path:
        pd_count = _process_plantdoc(plantdoc_path, all_images)
        print(f"PlantDoc: {pd_count} images collected")
    else:
        pd_count = 0
        print("PlantDoc: skipped (no path provided)")

    # Process custom Indian dataset
    if custom_path:
        custom_count = _process_custom(custom_path, all_images)
        print(f"Custom Indian: {custom_count} images collected")
    else:
        custom_count = 0
        print("Custom Indian: skipped (no path provided)")

    total = len(all_images)
    print(f"\nTotal images: {total}")

    if total == 0:
        print("WARNING: No images collected. Provide at least one dataset path.")
        return {"total": 0}

    # Group by class for stratified split
    by_class: dict[str, list[tuple[str, str]]] = {}
    for img_path, class_slug, source in all_images:
        by_class.setdefault(class_slug, []).append((img_path, source))

    # Stratified train/val/test split
    train_count = 0
    val_count = 0
    test_count = 0
    class_counts: dict[str, dict[str, int]] = {}

    for class_slug, images in sorted(by_class.items()):
        random.shuffle(images)
        n = len(images)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        # n_test = n - n_train - n_val  (remainder)

        class_counts[class_slug] = {"total": n, "train": 0, "val": 0, "test": 0}

        for i, (img_path, source) in enumerate(images):
            if i < n_train:
                split = "train"
            elif i < n_train + n_val:
                split = "val"
            else:
                split = "test"

            dest_dir = output / split / class_slug
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Copy with unique filename
            ext = Path(img_path).suffix
            dest_name = f"{source}_{i:06d}{ext}"
            dest_path = dest_dir / dest_name
            shutil.copy2(img_path, dest_path)

            class_counts[class_slug][split] += 1
            if split == "train":
                train_count += 1
            elif split == "val":
                val_count += 1
            else:
                test_count += 1

    # Save class mapping
    class_mapping = {slug: slug for slug in sorted(by_class.keys())}
    with open(output / "class_mapping.json", "w") as f:
        json.dump(class_mapping, f, indent=2)

    # Save dataset stats
    stats = {
        "total_images": total,
        "train_images": train_count,
        "val_images": val_count,
        "test_images": test_count,
        "num_classes": len(by_class),
        "sources": {
            "plantvillage": pv_count,
            "plantdoc": pd_count,
            "custom_indian": custom_count,
        },
        "class_counts": class_counts,
        "split_ratios": {"train": train_ratio, "val": val_ratio, "test": test_ratio},
        "random_seed": RANDOM_SEED,
    }
    with open(output / "dataset_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nDataset prepared at: {output}")
    print(f"  Classes: {len(by_class)}")
    print(f"  Train: {train_count}")
    print(f"  Val: {val_count}")
    print(f"  Test: {test_count}")
    print(f"  Stats saved to: {output / 'dataset_stats.json'}")

    return stats


def _process_plantvillage(path: str, all_images: list) -> int:
    """Process PlantVillage dataset."""
    count = 0
    pv_root = Path(path)

    # Try Color/ subdirectory first, then root
    color_dir = pv_root / "Color"
    search_dir = color_dir if color_dir.exists() else pv_root

    for class_dir in sorted(search_dir.iterdir()):
        if not class_dir.is_dir():
            continue

        class_name = class_dir.name
        mapped_slug = PLANTVILLAGE_MAP.get(class_name)

        if not mapped_slug:
            print(f"  WARNING: No mapping for PlantVillage class: {class_name}")
            continue

        for img_file in class_dir.iterdir():
            if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                all_images.append((str(img_file), mapped_slug, "pv"))
                count += 1

    return count


def _process_plantdoc(path: str, all_images: list) -> int:
    """Process PlantDoc dataset."""
    count = 0
    pd_root = Path(path)

    # PlantDoc has train/ and test/ subdirectories
    for split_dir in ("train", "test"):
        split_path = pd_root / split_dir
        if not split_path.exists():
            continue

        for class_dir in sorted(split_path.iterdir()):
            if not class_dir.is_dir():
                continue

            class_name = class_dir.name
            mapped_slug = PLANTDOC_MAP.get(class_name)

            if not mapped_slug:
                print(f"  WARNING: No mapping for PlantDoc class: {class_name}")
                continue

            for img_file in class_dir.iterdir():
                if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                    all_images.append((str(img_file), mapped_slug, "pd"))
                    count += 1

    return count


def _process_custom(path: str, all_images: list) -> int:
    """Process custom Indian crop disease dataset.

    Expected structure:
        custom_path/
            rice_blast/
                img001.jpg
                ...
            tomato_early_blight/
                ...
    """
    count = 0
    custom_root = Path(path)

    for class_dir in sorted(custom_root.iterdir()):
        if not class_dir.is_dir():
            continue

        class_slug = class_dir.name  # Already in our slug format

        for img_file in class_dir.iterdir():
            if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                all_images.append((str(img_file), class_slug, "custom"))
                count += 1

    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Prepare unified crop disease dataset from multiple sources"
    )
    parser.add_argument(
        "--plantvillage-path", type=str, default=None,
        help="Path to PlantVillage dataset root"
    )
    parser.add_argument(
        "--plantdoc-path", type=str, default=None,
        help="Path to PlantDoc dataset root"
    )
    parser.add_argument(
        "--custom-path", type=str, default=None,
        help="Path to custom Indian crop disease dataset"
    )
    parser.add_argument(
        "--output-path", type=str, default="./data/processed",
        help="Output path for processed dataset"
    )
    parser.add_argument(
        "--train-ratio", type=float, default=0.70,
        help="Train split ratio (default: 0.70)"
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.15,
        help="Validation split ratio (default: 0.15)"
    )
    parser.add_argument(
        "--test-ratio", type=float, default=0.15,
        help="Test split ratio (default: 0.15)"
    )
    args = parser.parse_args()

    stats = prepare_dataset(
        plantvillage_path=args.plantvillage_path,
        plantdoc_path=args.plantdoc_path,
        custom_path=args.custom_path,
        output_path=args.output_path,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )
    print(f"\nDone! Dataset stats: {json.dumps(stats, indent=2)}")
