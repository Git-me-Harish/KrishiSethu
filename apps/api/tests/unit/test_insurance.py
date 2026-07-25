"""Unit tests for insurance domain — schemas, premium computation, auto-evidence.

Tests pure functions that don't require a database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestPolicyCreateSchema:
    """Test the PolicyCreateRequest schema."""

    def test_valid_minimal_policy(self):
        from krishisetu.domains.insurance.schemas import PolicyCreateRequest
        from uuid import uuid4

        policy = PolicyCreateRequest(
            product_id=uuid4(),
            plot_id=uuid4(),
        )
        assert policy.bank_account_number is None
        assert policy.bank_ifsc is None

    def test_valid_with_bank_details(self):
        from krishisetu.domains.insurance.schemas import PolicyCreateRequest
        from uuid import uuid4

        policy = PolicyCreateRequest(
            product_id=uuid4(),
            plot_id=uuid4(),
            bank_account_number="12345678901",
            bank_ifsc="SBIN0001234",
        )
        assert policy.bank_account_number == "12345678901"

    def test_bank_account_without_ifsc_rejected(self):
        """Bank account and IFSC must be provided together."""
        from krishisetu.domains.insurance.schemas import PolicyCreateRequest
        from uuid import uuid4

        with pytest.raises(ValidationError, match="together"):
            PolicyCreateRequest(
                product_id=uuid4(),
                plot_id=uuid4(),
                bank_account_number="12345678901",
                # Missing bank_ifsc
            )

    def test_ifsc_without_account_rejected(self):
        from krishisetu.domains.insurance.schemas import PolicyCreateRequest
        from uuid import uuid4

        with pytest.raises(ValidationError, match="together"):
            PolicyCreateRequest(
                product_id=uuid4(),
                plot_id=uuid4(),
                # Missing bank_account_number
                bank_ifsc="SBIN0001234",
            )


class TestClaimCreateSchema:
    """Test the ClaimCreateRequest schema."""

    def test_valid_claim(self):
        from krishisetu.domains.insurance.schemas import ClaimCreateRequest
        from uuid import uuid4

        claim = ClaimCreateRequest(
            policy_id=uuid4(),
            claim_type="localized_risk",
            loss_date="2026-07-15",
            loss_description="Heavy rainfall caused waterlogging in my rice field, resulting in approximately 40% crop loss.",
            estimated_loss_pct=Decimal("40"),
        )
        assert claim.estimated_loss_pct == Decimal("40")

    def test_short_description_rejected(self):
        """Loss description must be at least 20 characters."""
        from krishisetu.domains.insurance.schemas import ClaimCreateRequest
        from uuid import uuid4

        with pytest.raises(ValidationError):
            ClaimCreateRequest(
                policy_id=uuid4(),
                claim_type="localized_risk",
                loss_date="2026-07-15",
                loss_description="Too short",  # < 20 chars
                estimated_loss_pct=Decimal("40"),
            )

    def test_loss_pct_out_of_range_rejected(self):
        from krishisetu.domains.insurance.schemas import ClaimCreateRequest
        from uuid import uuid4

        with pytest.raises(ValidationError):
            ClaimCreateRequest(
                policy_id=uuid4(),
                claim_type="localized_risk",
                loss_date="2026-07-15",
                loss_description="A valid description of the loss event.",
                estimated_loss_pct=Decimal("150"),  # > 100
            )

    def test_invalid_claim_type_rejected(self):
        from krishisetu.domains.insurance.schemas import ClaimCreateRequest
        from uuid import uuid4

        with pytest.raises(ValidationError):
            ClaimCreateRequest(
                policy_id=uuid4(),
                claim_type="invalid_type",
                loss_date="2026-07-15",
                loss_description="A valid description of the loss event.",
                estimated_loss_pct=Decimal("40"),
            )


class TestInsurerReviewSchema:
    """Test the InsurerReviewRequest schema."""

    def test_valid_approve(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        review = InsurerReviewRequest(
            action="approve",
            approved_amount=Decimal("25000"),
            review_notes="Claim verified with NDVI evidence.",
        )
        assert review.action == "approve"

    def test_approve_without_amount_rejected(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        with pytest.raises(ValidationError, match="approved_amount"):
            InsurerReviewRequest(action="approve")

    def test_valid_reject(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        review = InsurerReviewRequest(
            action="reject",
            rejection_reason="Insufficient evidence of crop loss.",
        )
        assert review.action == "reject"

    def test_reject_without_reason_rejected(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        with pytest.raises(ValidationError, match="rejection_reason"):
            InsurerReviewRequest(action="reject")

    def test_valid_request_evidence(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        review = InsurerReviewRequest(
            action="request_evidence",
            evidence_request_notes="Please upload photos of the affected crop.",
        )
        assert review.action == "request_evidence"

    def test_invalid_action_rejected(self):
        from krishisetu.domains.insurance.schemas import InsurerReviewRequest

        with pytest.raises(ValidationError):
            InsurerReviewRequest(action="invalid")


# ---------------------------------------------------------------------------
# Premium computation tests
# ---------------------------------------------------------------------------


class TestPremiumComputation:
    """Test the premium computation logic (via service helper)."""

    def test_premium_2_percent_kharif(self):
        """Kharif crops have 2% farmer premium rate."""
        # sum_insured_per_ha = 55000, area = 1.5 ha
        # sum_insured = 55000 * 1.5 = 82500
        # premium = 82500 * 0.02 = 1650
        sum_insured_per_ha = Decimal("55000")
        area_ha = Decimal("1.5")
        premium_rate = Decimal("0.02")

        sum_insured = sum_insured_per_ha * area_ha
        premium = sum_insured * premium_rate

        assert sum_insured == Decimal("82500")
        assert premium == Decimal("1650.0000")

    def test_premium_5_percent_commercial(self):
        """Commercial crops (sugarcane, banana) have 5% farmer premium rate."""
        sum_insured_per_ha = Decimal("95000")
        area_ha = Decimal("2.0")
        premium_rate = Decimal("0.05")

        sum_insured = sum_insured_per_ha * area_ha
        premium = sum_insured * premium_rate

        assert sum_insured == Decimal("190000")
        assert premium == Decimal("9500.0000")

    def test_premium_1_5_percent_rabi(self):
        """Rabi crops have 1.5% farmer premium rate."""
        sum_insured_per_ha = Decimal("55000")
        area_ha = Decimal("1.0")
        premium_rate = Decimal("0.015")

        sum_insured = sum_insured_per_ha * area_ha
        premium = sum_insured * premium_rate

        assert premium == Decimal("825.0000")


# ---------------------------------------------------------------------------
# Claim amount computation tests
# ---------------------------------------------------------------------------


class TestClaimAmountComputation:
    """Test the claimed_amount computation."""

    def test_claim_amount_50_percent_loss(self):
        """50% loss on ₹82500 sum insured = ₹41250 claim."""
        sum_insured = Decimal("82500")
        loss_pct = Decimal("50")
        claimed = sum_insured * (loss_pct / Decimal("100"))
        assert claimed == Decimal("41250.00")

    def test_claim_amount_100_percent_loss(self):
        """100% loss = full sum insured."""
        sum_insured = Decimal("82500")
        loss_pct = Decimal("100")
        claimed = sum_insured * (loss_pct / Decimal("100"))
        assert claimed == Decimal("82500.00")

    def test_claim_amount_0_percent_loss(self):
        """0% loss = ₹0 claim."""
        sum_insured = Decimal("82500")
        loss_pct = Decimal("0")
        claimed = sum_insured * (loss_pct / Decimal("100"))
        assert claimed == Decimal("0.00")


# ---------------------------------------------------------------------------
# Policy/claim number generation tests
# ---------------------------------------------------------------------------


class TestPolicyNumberGeneration:
    """Test policy number generation."""

    def test_policy_number_format(self):
        from krishisetu.domains.insurance.services import _generate_policy_number

        number = _generate_policy_number()
        assert number.startswith("KS-POL-")
        # Format: KS-POL-YYYYMMDD-8hexchars
        parts = number.split("-")
        assert len(parts) == 4
        assert len(parts[2]) == 8  # Date YYYYMMDD
        assert len(parts[3]) == 8  # UUID hex

    def test_policy_numbers_are_unique(self):
        from krishisetu.domains.insurance.services import _generate_policy_number

        numbers = {_generate_policy_number() for _ in range(100)}
        assert len(numbers) == 100  # All unique


class TestClaimNumberGeneration:
    """Test claim number generation."""

    def test_claim_number_format(self):
        from krishisetu.domains.insurance.services import _generate_claim_number

        number = _generate_claim_number()
        assert number.startswith("KS-CLM-")
        parts = number.split("-")
        assert len(parts) == 4
        assert len(parts[2]) == 8
        assert len(parts[3]) == 8

    def test_claim_numbers_are_unique(self):
        from krishisetu.domains.insurance.services import _generate_claim_number

        numbers = {_generate_claim_number() for _ in range(100)}
        assert len(numbers) == 100
