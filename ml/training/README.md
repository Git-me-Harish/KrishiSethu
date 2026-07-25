# KrishiSetu ML Training Pipeline

This directory contains the complete ML training pipeline for the crop disease
classifier, from dataset preparation to ONNX export and deployment.

## Pipeline Overview

```
Raw Datasets → Prepare → Train → Evaluate → Calibrate → Export ONNX → Deploy
     │              │         │          │            │            │
     │              │         │          │            │            └─ Upload to S3
     │              │         │          │            └─ Temperature scaling
     │              │         │          └─ Per-class metrics, confusion matrix
     │              │         └─ YOLOv8x-cls fine-tune with augmentations
     │              └─ Combine + split (70/15/15) + class mapping
     └─ PlantVillage + PlantDoc + Custom Indian
```

## Prerequisites

```bash
# Create a dedicated training virtual environment
python -m venv .venv-training
source .venv-training/bin/activate  # Linux/Mac
# .venv-training\Scripts\activate   # Windows

# Install training dependencies
pip install torch torchvision ultralytics mlflow scikit-learn onnxruntime pillow dvc
```

**GPU recommended**: Training YOLOv8x-cls on 67K images takes ~4 hours on
an NVIDIA A10G GPU. On CPU, it would take ~4 days.

## Step-by-Step Training

### 1. Download Datasets

```bash
# PlantVillage (54K images, 38 classes)
# Download from: https://www.kaggle.com/datasets/abdallahalidev/plantvillage-dataset
# Extract to: data/PlantVillage/

# PlantDoc (2.6K images, 27 classes)
# Download from: https://github.com/pratikkayal/PlantDoc-Dataset
# Extract to: data/PlantDoc/

# Custom Indian dataset (optional, ~10K images)
# Collect from ICAR research stations / farmer submissions
# Structure as: data/custom_indian/{disease_slug}/image.jpg
```

### 2. Prepare Dataset

```bash
python -m ml.training.dataset_preparation \
    --plantvillage-path data/PlantVillage \
    --plantdoc-path data/PlantDoc \
    --custom-path data/custom_indian \
    --output-path data/processed
```

This creates:
```
data/processed/
    train/
        tomato_early_blight/
            pv_000001.jpg
            ...
        rice_blast/
            custom_000001.jpg
            ...
    val/
        ...
    test/
        ...
    class_mapping.json
    dataset_stats.json
```

### 3. Train Model

```bash
python -m ml.training.train_disease_classifier \
    --data-path data/processed \
    --output-path models/disease_classifier_v1 \
    --epochs 100 \
    --batch-size 32 \
    --device 0
```

Key training parameters:
- **Model**: YOLOv8x-cls (pretrained on ImageNet)
- **Input size**: 640×640 (letterbox padded)
- **Augmentation**: Heavy (rotation ±30°, color jitter, blur, mixup)
- **Loss**: Cross-entropy with label smoothing (0.1)
- **LR schedule**: Cosine with warmup (3 epochs)
- **Early stopping**: Patience 20 epochs
- **Batch size**: 32 (adjust based on GPU memory)

### 4. Evaluate

```bash
python -m ml.evaluation.evaluate_disease_classifier \
    --model-path models/disease_classifier_v1/best.pt \
    --data-path data/processed \
    --output-path models/disease_classifier_v1/evaluation
```

Produces:
- Top-1 and Top-5 accuracy
- Per-class precision/recall/F1
- Confusion matrix
- Threshold checks (Top-1 ≥ 92%, Macro-F1 ≥ 0.88)

### 5. Calibrate Confidence

```bash
python -m ml.training.calibrate \
    --model-path models/disease_classifier_v1/best.pt \
    --data-path data/processed \
    --output-path models/disease_classifier_v1/calibration.json
```

Optimizes a temperature parameter T so that:
- 90% confidence predictions are correct 90% of the time
- ECE (Expected Calibration Error) ≤ 0.05

### 6. Export to ONNX

```bash
# Get class labels from dataset
LABELS=$(python -c "
import json
with open('data/processed/dataset_stats.json') as f:
    stats = json.load(f)
print(','.join(sorted(stats['class_counts'].keys())))
")

python -m ml.training.export_onnx \
    --model-path models/disease_classifier_v1/best.pt \
    --output-path models/disease_classifier_v1/model.onnx \
    --version v1.0.0 \
    --labels "$LABELS"
```

### 7. Deploy to ML Inference Service

```bash
# Upload ONNX model to S3
aws s3 cp models/disease_classifier_v1/model.onnx \
    s3://krishisetu-models/disease/v1.0.0.onnx

# Update ML service configuration
# In apps/ml-inference/.env:
#   DISEASE_CLASSIFIER_MODEL_PATH=s3://krishisetu-models/disease/v1.0.0.onnx
#   DISEASE_CLASSIFIER_MODEL_VERSION=v1.0.0
#   DISEASE_CLASSIFIER_LABELS=<comma-separated labels from step 6>

# Restart ML inference service
docker compose -f infra/docker-compose.yml restart ml-inference
```

## DVC Pipeline (Optional)

For full reproducibility with dataset versioning:

```bash
dvc init
dvc remote add -d storage s3://krishisetu-dvc/
dvc add data/PlantVillage data/PlantDoc data/custom_indian

# Run entire pipeline
dvc repro

# Push datasets and models to remote
dvc push
```

## Model Card

See `ml/registry/disease_classifier/card.md` for the full model card
documenting intended use, training data, evaluation metrics, limitations,
and ethical considerations.

## Training on Cloud GPU

For training without a local GPU:

```bash
# AWS EC2 with GPU
aws ec2 run-instances \
    --image-id ami-0abcdef1234567890 \
    --instance-type g5.xlarge \
    --key-name my-key \
    --block-device-mappings DeviceName=/dev/sda1,Ebs={VolumeSize=100}

# SSH into instance, clone repo, run training
ssh -i my-key.pem ec2-user@<instance-ip>
git clone <repo-url> && cd krishisetu
pip install torch torchvision ultralytics mlflow scikit-learn onnxruntime
python -m ml.training.train_disease_classifier ...
```

Estimated cost: ~$1.50 for 4 hours on g5.xlarge (NVIDIA A10G).
