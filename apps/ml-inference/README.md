# KrishiSetu ML Inference Service

FastAPI microservice for ML model serving, primarily the YOLOv8 crop disease
classifier. Separate from the main API for independent scaling (GPU vs CPU
pools) and model versioning.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root info |
| `/docs` | GET | Swagger UI (dev only) |
| `/health` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe (checks model loaded) |
| `/predict/disease` | POST | Disease classification from image |

## Local Development

### With Docker Compose (recommended)

From the repository root:

```bash
docker compose -f infra/docker-compose.yml up -d ml-inference
```

### Without Docker

```bash
cd apps/ml-inference

python3.12 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

cp .env.example .env
# Edit .env to point S3_ENDPOINT to your MinIO/S3

uvicorn krishisetu_ml.main:app --reload --port 8001
```

## Model Management

Models are loaded from the path specified in `DISEASE_CLASSIFIER_MODEL_PATH`:

- **Local file**: `/app/models/disease_classifier_v1.onnx`
- **S3 URI**: `s3://krishisetu-models/disease/v1.onnx` (auto-downloaded to local cache)

On startup, the model is warmed up with a dummy inference to avoid cold-start
latency on the first real request.

### Training a New Model

See `ml/training/disease_classifier.py` for the training script. After training:

1. Export to ONNX: `torch.onnx.export(model, ...)`
2. Upload to S3: `aws s3 cp model.onnx s3://krishisetu-models/disease/v2.onnx`
3. Update `DISEASE_CLASSIFIER_MODEL_PATH` and `DISEASE_CLASSIFIER_MODEL_VERSION`
4. Restart the service

## Model Card

See `ml/registry/disease_classifier/card.md` for the full model card documenting:
- Intended use
- Training data
- Evaluation metrics
- Known limitations
- Ethical considerations
