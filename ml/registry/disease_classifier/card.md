# Disease Classifier — Model Card

## Model Details

| Field | Value |
|-------|-------|
| **Model name** | `disease_classifier` |
| **Version** | `v1.0.0` (first production model) |
| **Architecture** | YOLOv8x-cls (classification variant, extra-large) |
| **Framework** | PyTorch 2.5 + Ultralytics 8.3, exported to ONNX |
| **Input** | RGB image, 640×640, normalized (ImageNet mean/std) |
| **Output** | Softmax probabilities over disease classes |
| **Calibration** | Temperature scaling (T optimized on validation set, ECE ≤ 0.05) |
| **Inference runtime** | ONNX Runtime 1.20 (CPUExecutionProvider; CUDA optional) |
| **Latency target** | P95 < 500ms on CPU, P95 < 100ms on GPU |
| **Training script** | `ml/training/train_disease_classifier.py` |
| **Evaluation script** | `ml/evaluation/evaluate_disease_classifier.py` |
| **Calibration script** | `ml/training/calibrate.py` |
| **ONNX export script** | `ml/training/export_onnx.py` |

## Intended Use

- **Primary use**: Classify crop diseases from farmer-submitted leaf photos in the KrishiSetu platform.
- **Target users**: Indian farmers (smallholder and medium-holding), agricultural extension officers.
- **Out of scope**: Human medical diagnosis, veterinary diagnosis, post-harvest storage rot detection, abiotic stress diagnosis (drought, flood, chemical injury).

## Training Data

| Dataset | Source | Size | Notes |
|---------|--------|------|-------|
| PlantVillage | [Hughes & Salathé 2015](https://www.plantvillage.org) | 54,303 images, 38 classes | Lab-controlled conditions, single leaf per image |
| PlantDoc | [Singh et al. 2020](https://github.com/pratikkayal/PlantDoc-Dataset) | 2,598 images, 27 classes | Real-world field images, more realistic |
| Custom Indian dataset | ICAR research stations + farmer submissions | ~10,000 images target | Indian-specific crops (tur, groundnut, ragi) underrepresented in global datasets |

**Total training set**: ~67,000 images (target after custom dataset collection).

**Class mapping**: PlantVillage and PlantDoc class names are mapped to
KrishiSetu disease catalog slugs via `ml/training/dataset_preparation.py`.
See `PLANTVILLAGE_MAP` and `PLANTDOC_MAP` in that file for the full mapping.

**Train/val/test split**: 70/15/15, stratified by class, with random seed 42
for reproducibility.

## Training Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Pretrained weights | `yolov8x-cls.pt` (ImageNet) | Transfer learning from general vision features |
| Epochs | 100 | Sufficient for convergence with early stopping |
| Batch size | 32 | Balanced between GPU memory and gradient stability |
| Learning rate | 0.001 (cosine decay to 0.00001) | Standard for fine-tuning |
| Warmup | 3 epochs | Prevent early divergence from pretrained weights |
| Weight decay | 0.0005 | L2 regularization |
| Dropout | 0.2 | Prevent overfitting |
| Label smoothing | 0.1 | Improve generalization |
| Early stopping patience | 20 epochs | Stop when val accuracy plateaus |

### Augmentation

Heavy augmentation is critical because farmer-submitted photos vary widely
in lighting, angle, and quality.

| Augmentation | Value | Rationale |
|-------------|-------|-----------|
| Rotation | ±30° | Farmer may hold phone at any angle |
| Horizontal flip | 50% probability | Leaf symmetry |
| Vertical flip | 10% probability | Rare but possible |
| HSV hue | ±1.5% | Lighting variation |
| HSV saturation | ±70% | Camera quality variation |
| HSV value | ±40% | Brightness variation |
| Scale | ±20% | Distance variation |
| Translation | ±10% | Framing variation |
| Shear | ±5° | Perspective variation |
| Mixup | 10% probability | Improve robustness |

## Evaluation

### Metrics (target — pending real model training)

| Metric | Threshold | How to Check |
|--------|-----------|--------------|
| Top-1 accuracy | ≥ 92% | `ml/evaluation/evaluate_disease_classifier.py` |
| Top-5 accuracy | ≥ 98% | Same script |
| Macro-F1 | ≥ 0.88 | Same script |
| Minimum per-class F1 | ≥ 0.75 | Same script |
| Calibration ECE | ≤ 0.05 | `ml/training/calibrate.py` |

### Test set

- Held-out 15% of dataset, stratified by class.
- No augmentation applied to test set.
- Per-class confusion matrix analyzed to identify commonly confused diseases.

### Calibration

Temperature scaling is applied post-training:
1. Collect model logits on validation set
2. Optimize temperature T to minimize NLL loss
3. Apply `softmax(logits / T)` for all predictions

This ensures that a 90% confidence prediction is correct ~90% of the time,
which is critical for our 70% confidence threshold for officer review.

### Production monitoring

- **Confidence distribution**: tracked via Prometheus histogram; drift detection via PSI.
- **Farmer feedback**: thumbs-up/down on each prediction; correct/incorrect/partially_correct.
- **Officer review rate**: percentage of predictions below 70% confidence threshold.
- **Per-class accuracy**: tracked monthly based on farmer feedback and officer reviews.

## Limitations

1. **Image quality dependency**: Model performs best with well-lit, focused, close-up photos. Performance degrades significantly with blurry, dark, or distant images.
2. **Single-leaf assumption**: Model trained primarily on single-leaf images. Multi-leaf or whole-plant photos may produce less accurate results.
3. **Indian crop coverage**: While the custom dataset targets Indian crops, coverage is incomplete for some region-specific varieties and lesser-known diseases.
4. **Abiotic stress**: Model does not distinguish nutrient deficiencies, drought stress, or chemical injury — these may be misclassified as biotic diseases.
5. **Background sensitivity**: Model may be sensitive to backgrounds (soil, sky, hands). Training data augmentation partially addresses this.
6. **Early-stage diseases**: Symptoms in early stages may be too subtle for reliable classification.

## Ethical Considerations

1. **Misdiagnosis risk**: A wrong diagnosis can lead to unnecessary pesticide application (economic loss, environmental harm) or failure to treat a real disease (crop loss). Mitigations:
   - Low-confidence predictions (< 70%) are routed to officer review.
   - Treatment recommendations are sourced from ICAR — verified, not model-generated.
   - UI clearly states "This is an AI prediction. For confirmation, consult an agricultural officer."
2. **Data privacy**: Uploaded images may contain metadata (EXIF) with location data. This is stripped before storage. Images are not shared with third parties.
3. **Bias**: If the training data over-represents certain regions or crop varieties, the model may perform poorly for underrepresented groups. Mitigation: targeted data collection in underrepresented regions.
4. **Economic impact**: Recommendations to apply chemical pesticides have direct economic consequences for farmers. The model prioritizes organic and cultural treatments where effective, and always includes safety precautions.

## Deployment

- **Inference service**: `apps/ml-inference/` (separate FastAPI microservice).
- **Model artifact**: ONNX file, stored in S3 (`s3://krishisetu-models/disease/v{X}.onnx`).
- **Versioning**: MLflow tracks model versions with full reproducibility (commit hash, dataset version, hyperparameters, metrics).
- **Rollback**: Any model version can be rolled back with a single env var change (`DISEASE_CLASSIFIER_MODEL_PATH`).
- **Approval workflow**: New model versions require sign-off from ML lead + agricultural domain expert before promotion to production.

## Training Pipeline (DVC)

The full pipeline is defined in `ml/dvc.yaml` and can be reproduced with:

```bash
dvc repro  # Runs: prepare → train → evaluate → calibrate → export_onnx
```

Each stage's dependencies and outputs are tracked, ensuring that any change
to data or code triggers the appropriate re-training.

## Contact

- **Model owner**: KrishiSetu ML team
- **Issue reporting**: `ml-issues@krishisetu.in`
- **Slack**: `#ml-disease-classifier`

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| v0.1.0-dummy | 2026-07-19 | Placeholder model for development. Returns dummy predictions. Used for end-to-end pipeline testing before real model is trained. |
| v1.0.0 | TBD | First production model trained on PlantVillage + PlantDoc + custom Indian dataset. Target: 92% top-1 accuracy, ECE ≤ 0.05. |
