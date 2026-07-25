# ML Registry

This directory contains model cards and version metadata for all ML models
deployed in the KrishiSetu platform.

## Models

| Model | Purpose | Status | Card |
|-------|---------|--------|------|
| `disease_classifier` | Crop disease classification from leaf photos | v0.1.0-dummy (placeholder) | [card](disease_classifier/card.md) |
| `soil_classifier` | Soil type classification from imagery | Not started | TBD |
| `voice_asr` | Multilingual speech recognition (10 languages) | Not started | TBD |
| `voice_tts` | Multilingual text-to-speech | Not started (will use managed Azure TTS) | TBD |
| `query_nlu` | Vernacular natural language understanding | Not started | TBD |

## Model Card Format

Each model has a `card.md` file documenting:

1. **Model Details** — name, version, architecture, framework
2. **Intended Use** — primary use case, target users, out-of-scope uses
3. **Training Data** — datasets used, size, class balance
4. **Evaluation** — metrics, test set, production monitoring
5. **Limitations** — known weaknesses and failure modes
6. **Ethical Considerations** — risks, mitigations, bias, privacy
7. **Deployment** — how the model is served, versioned, rolled back
8. **Contact** — owner, issue reporting
9. **Changelog** — version history

## Model Governance

Every model deployed to production must have:

- An up-to-date model card in this directory
- A versioned release in MLflow with: commit hash, dataset version, hyperparameters, training metrics, evaluation metrics
- Sign-off from the ML lead and the domain lead (e.g., agricultural expert for disease classifier)
- A rollback plan documented in the card

## Adding a New Model

1. Create a directory: `mkdir -p ml/registry/<model_name>`
2. Write the model card: `ml/registry/<model_name>/card.md`
3. Train the model and log to MLflow
4. Export to ONNX
5. Upload to S3: `s3://krishisetu-models/<model_name>/v<X>.onnx`
6. Update the inference service config (`apps/ml-inference/.env`)
7. Restart the inference service
8. Verify via `/health/ready` endpoint
