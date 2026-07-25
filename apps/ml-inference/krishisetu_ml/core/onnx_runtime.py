"""ONNX Runtime session management.

Handles loading ONNX models from local filesystem or S3, with:
- Lazy initialization (model loaded on first inference)
- Thread-safe session access
- Warmup on startup (configurable)
- S3 download with caching for remote models
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import onnxruntime as ort
from onnxruntime import InferenceSession, SessionOptions

from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import get_logger

logger = get_logger(__name__)


class ModelLoader:
    """Manages ONNX Runtime sessions for all loaded models.

    Models are loaded lazily on first access and cached. If the model path
    is an S3 URI (s3://bucket/key), the model is downloaded to a local cache
    directory first.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, InferenceSession] = {}
        self._lock = threading.Lock()
        self._cache_dir = Path("/tmp/krishisetu_models")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_session(self, model_name: str) -> InferenceSession:
        """Get (or load) the ONNX session for a model.

        Thread-safe — concurrent calls will block until the first one loads
        the model, then all callers share the same session.
        """
        if model_name in self._sessions:
            return self._sessions[model_name]

        with self._lock:
            # Double-check after acquiring lock
            if model_name in self._sessions:
                return self._sessions[model_name]

            session = self._load_session(model_name)
            self._sessions[model_name] = session
            return session

    def _load_session(self, model_name: str) -> InferenceSession:
        """Load an ONNX model into an InferenceSession."""
        # Resolve model path from settings
        model_path = self._resolve_model_path(model_name)
        if not model_path:
            raise FileNotFoundError(f"Model '{model_name}' not configured")

        logger.info(
            "model.loading",
            model_name=model_name,
            path=str(model_path),
        )

        # Configure session options for production performance
        session_options = SessionOptions()
        session_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        # Use all available CPU cores (or set intra_op_num_threads explicitly)
        session_options.intra_op_num_threads = 0  # 0 = auto

        # Determine execution provider
        providers = self._get_providers()

        session = InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=providers,
        )

        logger.info(
            "model.loaded",
            model_name=model_name,
            providers=providers,
            input_names=[i.name for i in session.get_inputs()],
            output_names=[o.name for o in session.get_outputs()],
        )

        return session

    def _resolve_model_path(self, model_name: str) -> Path | None:
        """Resolve model path from settings, downloading from S3 if needed."""
        path_str: str | None = None

        if model_name == "disease_classifier":
            path_str = settings().DISEASE_CLASSIFIER_MODEL_PATH
        else:
            raise ValueError(f"Unknown model: {model_name}")

        if not path_str:
            return None

        # S3 URI — download to local cache
        if path_str.startswith("s3://"):
            return self._download_from_s3(path_str)

        # Local path
        path = Path(path_str)
        if not path.exists():
            logger.warning(
                "model.file_not_found",
                model_name=model_name,
                path=str(path),
                note="Model file does not exist. Service will return error on inference.",
            )
            return path  # Return anyway so the error is clear on inference

        return path

    def _download_from_s3(self, s3_uri: str) -> Path:
        """Download a model artifact from S3 to local cache."""
        import boto3
        from botocore.config import Config as BotoConfig

        # Parse S3 URI: s3://bucket/key/path
        parts = s3_uri.removeprefix("s3://").split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")
        bucket, key = parts

        # Cache path — same filename as the S3 key
        cache_path = self._cache_dir / Path(key).name
        if cache_path.exists():
            logger.info(
                "model.s3_cache_hit",
                s3_uri=s3_uri,
                cache_path=str(cache_path),
            )
            return cache_path

        logger.info(
            "model.s3_download",
            s3_uri=s3_uri,
            cache_path=str(cache_path),
        )

        client = boto3.client(
            "s3",
            endpoint_url=settings().S3_ENDPOINT,
            aws_access_key_id=settings().S3_ACCESS_KEY.get_secret_value(),
            aws_secret_access_key=settings().S3_SECRET_KEY.get_secret_value(),
            region_name=settings().S3_REGION,
            config=BotoConfig(signature_version="s3v4"),
        )
        client.download_file(bucket, key, str(cache_path))

        return cache_path

    def _get_providers(self) -> list[str]:
        """Get the list of execution providers to try, in priority order."""
        available = ort.get_available_providers()
        # Prefer CUDA if available, fall back to CPU
        if "CUDAExecutionProvider" in available and settings().is_production:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def warmup(self, model_name: str) -> None:
        """Run a dummy inference to warm up the model.

        Called on startup to avoid cold-start latency on the first real
        request.
        """
        try:
            session = self.get_session(model_name)
            inputs = session.get_inputs()
            if not inputs:
                return

            # Create a dummy input of the right shape
            import numpy as np

            input_shape = inputs[0].shape
            # Replace dynamic dimensions (None, -1, strings) with 1
            dummy_shape = [
                1 if (dim is None or dim == -1 or isinstance(dim, str)) else dim
                for dim in input_shape
            ]
            # Default to float32
            dummy_input = np.zeros(dummy_shape, dtype=np.float32)
            session.run(None, {inputs[0].name: dummy_input})

            logger.info(
                "model.warmed_up",
                model_name=model_name,
                input_shape=input_shape,
            )
        except Exception as e:
            logger.warning(
                "model.warmup_failed",
                model_name=model_name,
                error=str(e),
                note="Service will start anyway; first inference will be slower",
            )


# Singleton instance
_loader: ModelLoader | None = None


def get_model_loader() -> ModelLoader:
    """Get the singleton ModelLoader instance."""
    global _loader
    if _loader is None:
        _loader = ModelLoader()
    return _loader
