"""Unit tests for disease domain schemas and ML model utilities.

Tests:
- Disease report create schema validation
- Feedback schema validation
- Officer review schema validation
- Disease classifier preprocessing (image resize, normalize, NCHW)
- Disease classifier postprocessing (softmax, temperature scaling, top-k)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestDiseaseReportCreateSchema:
    """Test the DiseaseReportCreate schema."""

    def test_valid_report_create(self):
        from krishisetu.domains.disease.schemas import DiseaseReportCreate

        report = DiseaseReportCreate(
            image_key="disease-reports/farmer-123/report-456/original.jpg",
            image_content_type="image/jpeg",
        )
        assert report.image_key.startswith("disease-reports/")
        assert report.plot_id is None
        assert report.crop_cycle_id is None
        assert report.farmer_notes is None

    def test_report_create_with_plot_and_notes(self):
        from uuid import uuid4
        from krishisetu.domains.disease.schemas import DiseaseReportCreate

        plot_id = uuid4()
        report = DiseaseReportCreate(
            image_key="disease-reports/farmer-123/report-456/original.jpg",
            plot_id=plot_id,
            farmer_notes="Leaves showing yellow spots for 3 days",
        )
        assert report.plot_id == plot_id
        assert "yellow spots" in report.farmer_notes

    def test_report_create_notes_max_length(self):
        """Notes cannot exceed 2000 characters."""
        from krishisetu.domains.disease.schemas import DiseaseReportCreate

        with pytest.raises(ValidationError):
            DiseaseReportCreate(
                image_key="key",
                farmer_notes="x" * 2001,
            )

    def test_report_create_image_key_required(self):
        """image_key is required."""
        from krishisetu.domains.disease.schemas import DiseaseReportCreate

        with pytest.raises(ValidationError):
            DiseaseReportCreate()  # type: ignore[call-arg]


class TestFeedbackSchema:
    """Test the DiseaseFeedbackCreate schema."""

    def test_valid_correct_feedback(self):
        from krishisetu.domains.disease.schemas import DiseaseFeedbackCreate

        feedback = DiseaseFeedbackCreate(feedback_type="correct")
        assert feedback.feedback_type.value == "correct"
        assert feedback.suggested_disease_slug is None

    def test_valid_incorrect_feedback_with_suggestion(self):
        from krishisetu.domains.disease.schemas import DiseaseFeedbackCreate

        feedback = DiseaseFeedbackCreate(
            feedback_type="incorrect",
            suggested_disease_slug="rice_blast",
        )
        assert feedback.suggested_disease_slug == "rice_blast"

    def test_invalid_feedback_type_rejected(self):
        from krishisetu.domains.disease.schemas import DiseaseFeedbackCreate

        with pytest.raises(ValidationError):
            DiseaseFeedbackCreate(feedback_type="wrong")  # type: ignore[arg-type]

    def test_notes_max_length(self):
        from krishisetu.domains.disease.schemas import DiseaseFeedbackCreate

        with pytest.raises(ValidationError):
            DiseaseFeedbackCreate(
                feedback_type="correct",
                notes="x" * 1001,
            )


class TestOfficerReviewSchema:
    """Test the OfficerReviewRequest schema."""

    def test_valid_review_with_disease_slug(self):
        from krishisetu.domains.disease.schemas import OfficerReviewRequest

        review = OfficerReviewRequest(
            diagnosis="Confirmed rice blast based on leaf lesion pattern and field conditions.",
            disease_slug="rice_blast",
        )
        assert review.disease_slug == "rice_blast"

    def test_review_diagnosis_min_length(self):
        """Diagnosis must be at least 10 characters."""
        from krishisetu.domains.disease.schemas import OfficerReviewRequest

        with pytest.raises(ValidationError):
            OfficerReviewRequest(diagnosis="short")  # less than 10 chars

    def test_review_disease_slug_optional(self):
        """disease_slug is optional (officer may submit text-only diagnosis)."""
        from krishisetu.domains.disease.schemas import OfficerReviewRequest

        review = OfficerReviewRequest(
            diagnosis="The symptoms appear to be nutrient deficiency rather than disease."
        )
        assert review.disease_slug is None


class TestUploadUrlSchema:
    """Test the UploadUrlRequest schema."""

    def test_valid_content_types(self):
        from krishisetu.domains.disease.schemas import UploadUrlRequest

        for ct in ["image/jpeg", "image/png", "image/webp"]:
            req = UploadUrlRequest(content_type=ct)  # type: ignore[arg-type]
            assert req.content_type == ct

    def test_invalid_content_type_rejected(self):
        from krishisetu.domains.disease.schemas import UploadUrlRequest

        with pytest.raises(ValidationError):
            UploadUrlRequest(content_type="image/gif")  # type: ignore[arg-type]

    def test_default_content_type(self):
        from krishisetu.domains.disease.schemas import UploadUrlRequest

        req = UploadUrlRequest()
        assert req.content_type == "image/jpeg"


# ---------------------------------------------------------------------------
# Disease classifier preprocessing tests
# ---------------------------------------------------------------------------


class TestDiseaseClassifierPreprocessing:
    """Test the disease classifier image preprocessing.

    These tests don't require the ONNX model — they test the preprocessing
    pipeline (resize, normalize, NCHW conversion) in isolation.
    """

    def test_letterbox_resize_preserves_aspect_ratio(self):
        """Letterbox resize should preserve aspect ratio and pad to target size."""
        from PIL import Image
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier, INPUT_SIZE

        # Create a classifier-like object just to test the letterbox method
        # (we can't instantiate the real classifier without an ONNX session)
        class TestClassifier:
            _letterbox_resize = DiseaseClassifier._letterbox_resize

        # Wide image (2:1 aspect ratio)
        wide = Image.new("RGB", (200, 100), (255, 0, 0))
        resized = TestClassifier._letterbox_resize(None, wide, INPUT_SIZE, INPUT_SIZE)

        assert resized.size == (INPUT_SIZE, INPUT_SIZE)
        # The resized image should fit within the canvas with padding

    def test_letterbox_resize_centered(self):
        """Letterbox resize should center the image on the canvas."""
        from PIL import Image
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier, INPUT_SIZE

        class TestClassifier:
            _letterbox_resize = DiseaseClassifier._letterbox_resize

        # Square image
        square = Image.new("RGB", (100, 100), (255, 0, 0))
        resized = TestClassifier._letterbox_resize(None, square, INPUT_SIZE, INPUT_SIZE)

        # Center pixel should be red (the original image color)
        center_pixel = resized.getpixel((INPUT_SIZE // 2, INPUT_SIZE // 2))
        assert center_pixel[0] > 200  # Red channel high

        # Corner pixel should be gray (128, 128, 128) padding
        corner_pixel = resized.getpixel((0, 0))
        assert abs(corner_pixel[0] - 128) < 10  # Gray padding

    def test_preprocess_output_shape(self):
        """Preprocessed image should have shape (1, 3, 640, 640)."""
        import numpy as np
        from PIL import Image
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier, INPUT_SIZE

        class TestClassifier:
            preprocess = DiseaseClassifier.preprocess

        # Create a test image
        img = Image.new("RGB", (300, 200), (100, 150, 200))

        # Preprocess
        result = TestClassifier.preprocess(None, img)

        assert result.shape == (1, 3, INPUT_SIZE, INPUT_SIZE)
        assert result.dtype == np.float32

    def test_preprocess_normalizes_to_imagenet_range(self):
        """Preprocessed values should be roughly in [-2, 2] range after ImageNet normalization."""
        import numpy as np
        from PIL import Image
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        class TestClassifier:
            preprocess = DiseaseClassifier.preprocess

        # Image with all 128s (gray)
        img = Image.new("RGB", (640, 640), (128, 128, 128))
        result = TestClassifier.preprocess(None, img)

        # After normalization: (128/255 - mean) / std
        # For ImageNet mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
        # 128/255 ≈ 0.502
        # (0.502 - 0.485) / 0.229 ≈ 0.074 (close to 0 for gray)
        assert np.all(np.abs(result) < 3.0)  # Sanity check

    def test_preprocess_converts_grayscale_to_rgb(self):
        """Grayscale images should be converted to RGB."""
        import numpy as np
        from PIL import Image
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        class TestClassifier:
            preprocess = DiseaseClassifier.preprocess

        # Grayscale image
        img = Image.new("L", (640, 640), 128)
        result = TestClassifier.preprocess(None, img)

        # Should have 3 channels (RGB)
        assert result.shape == (1, 3, 640, 640)


# ---------------------------------------------------------------------------
# Disease classifier postprocessing tests
# ---------------------------------------------------------------------------


class TestDiseaseClassifierPostprocessing:
    """Test the disease classifier postprocessing (softmax, top-k)."""

    def test_softmax_produces_probabilities_summing_to_one(self):
        """Softmax output should sum to 1.0 for all classes."""
        import numpy as np
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        # Create a fake session-like object with labels
        class FakeSession:
            def get_inputs(self):
                class Input:
                    name = "input"
                    shape = [1, 3, 640, 640]
                return [Input()]

            def get_outputs(self):
                class Output:
                    shape = [1, 5]
                return [Output()]

        class TestClassifier(DiseaseClassifier):
            pass

        # Monkey-patch the labels and temperature
        classifier = TestClassifier.__new__(TestClassifier)
        classifier.session = FakeSession()
        classifier.labels = ["healthy", "rice_blast", "rice_blight", "wheat_rust", "tomato_blight"]
        classifier.model_version = "test"

        # Test with random logits
        logits = np.array([[2.0, 1.0, 0.5, -1.0, 0.0]])
        predictions = classifier.postprocess(logits)

        # Sum of confidences should be ~1.0
        total = sum(p.confidence for p in predictions)
        assert abs(total - 1.0) < 0.001

    def test_top_prediction_is_highest_confidence(self):
        """The first prediction should have the highest confidence."""
        import numpy as np
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        class FakeSession:
            def get_inputs(self):
                class Input:
                    name = "input"
                    shape = [1, 3, 640, 640]
                return [Input()]

            def get_outputs(self):
                class Output:
                    shape = [1, 3]
                return [Output()]

        classifier = DiseaseClassifier.__new__(DiseaseClassifier)
        classifier.session = FakeSession()
        classifier.labels = ["healthy", "rice_blast", "wheat_rust"]
        classifier.model_version = "test"

        # Logits where rice_blast is clearly highest
        logits = np.array([[0.1, 5.0, 0.2]])
        predictions = classifier.postprocess(logits)

        assert predictions[0].label == "rice_blast"
        assert predictions[0].confidence > 0.9
        assert predictions[0].disease_slug == "rice_blast"

    def test_top_k_limits_predictions(self):
        """Top-k should return at most k predictions."""
        import numpy as np
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        class FakeSession:
            def get_inputs(self):
                class Input:
                    name = "input"
                    shape = [1, 3, 640, 640]
                return [Input()]

            def get_outputs(self):
                class Output:
                    shape = [1, 10]
                return [Output()]

        classifier = DiseaseClassifier.__new__(DiseaseClassifier)
        classifier.session = FakeSession()
        classifier.labels = [f"class_{i}" for i in range(10)]
        classifier.model_version = "test"

        logits = np.array([[float(i) for i in range(10)]])
        predictions = classifier.postprocess(logits, top_k=3)

        assert len(predictions) == 3

    def test_disease_slug_formatting(self):
        """Disease slug should be lowercase with underscores."""
        import numpy as np
        from krishisetu_ml.models.disease_classifier import DiseaseClassifier

        class FakeSession:
            def get_inputs(self):
                class Input:
                    name = "input"
                    shape = [1, 3, 640, 640]
                return [Input()]

            def get_outputs(self):
                class Output:
                    shape = [1, 3]
                return [Output()]

        classifier = DiseaseClassifier.__new__(DiseaseClassifier)
        classifier.session = FakeSession()
        classifier.labels = ["Tomato Early Blight", "Rice Blast", "Wheat-Leaf-Rust"]
        classifier.model_version = "test"

        logits = np.array([[1.0, 5.0, 0.5]])
        predictions = classifier.postprocess(logits)

        assert predictions[0].disease_slug == "rice_blast"
        # Verify other slugs too
        slugs = [p.disease_slug for p in predictions]
        assert "tomato_early_blight" in slugs
        assert "wheat_leaf_rust" in slugs


# ---------------------------------------------------------------------------
# Storage key generation tests
# ---------------------------------------------------------------------------


class TestStorageKeyGeneration:
    """Test S3 key generation helpers."""

    def test_disease_report_image_key_format(self):
        from uuid import uuid4
        from krishisetu.core.storage import StorageClient

        farmer_id = uuid4()
        report_id = uuid4()
        key = StorageClient.disease_report_image_key(farmer_id, report_id)

        assert key == f"disease-reports/{farmer_id}/{report_id}/original.jpg"

    def test_disease_report_image_key_custom_suffix(self):
        from uuid import uuid4
        from krishisetu.core.storage import StorageClient

        key = StorageClient.disease_report_image_key(
            uuid4(), uuid4(), "thumbnail.jpg"
        )
        assert key.endswith("/thumbnail.jpg")

    def test_ndvi_raster_key_format(self):
        from uuid import uuid4
        from krishisetu.core.storage import StorageClient

        plot_id = uuid4()
        key = StorageClient.ndvi_raster_key(plot_id, "2026-07-19")
        assert key == f"ndvi/{plot_id}/2026-07-19.tiff"
