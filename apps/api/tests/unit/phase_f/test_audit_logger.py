"""Unit tests for the audit logger (Phase F).

These tests verify the API surface and edge-case handling of audit_log()
without requiring a real database. The actual DB writes are tested in
integration tests.

The audit_log function is designed to NEVER raise — it swallows DB errors
so the user's request can complete. This is the most important guarantee
to test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from krishisetu.core.audit_logger import (
    AuditAction,
    AuditOutcome,
    audit_log,
    audit_log_pii_access,
)


class TestAuditActionEnum:
    def test_all_values_are_strings(self) -> None:
        for action in AuditAction:
            assert isinstance(action.value, str)

    def test_categories_present(self) -> None:
        """Sanity check that all 9 categories of actions are defined."""
        all_actions = [a.value for a in AuditAction]
        # Login
        assert "login.success" in all_actions
        assert "login.failed" in all_actions
        # PII
        assert "pii.accessed" in all_actions
        assert "pii.updated" in all_actions
        # Consent
        assert "consent.granted" in all_actions
        assert "consent.withdrawn" in all_actions
        # DSR
        assert "dsr.access.requested" in all_actions
        assert "dsr.erasure.applied" in all_actions
        # Grievance
        assert "grievance.filed" in all_actions
        assert "grievance.resolved" in all_actions
        # Payment
        assert "payment.captured" in all_actions
        assert "escrow.released" in all_actions
        # Security
        assert "security.csrf.violation" in all_actions
        assert "security.rate_limit.exceeded" in all_actions


class TestAuditLogNeverRaises:
    """The most important guarantee: audit_log NEVER raises.

    If the DB write fails, the error is logged via structlog but the
    user's request continues. This is critical because audit failures
    must not break the user's flow.
    """

    async def test_db_failure_is_swallowed(self) -> None:
        # Mock a session whose execute() raises
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB connection lost")
        mock_db.commit = AsyncMock(side_effect=Exception("commit failed"))
        mock_db.rollback = AsyncMock()

        # Should NOT raise
        result = await audit_log(
            mock_db,
            action=AuditAction.PII_ACCESSED,
            actor_id="user-123",
            resource_type="farmer_profile",
            resource_id="profile-456",
        )
        # Returns a UUID (even though DB write failed)
        assert result is not None

    async def test_successful_write_returns_uuid(self) -> None:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        result = await audit_log(
            mock_db,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user-123",
            actor_role="farmer",
        )
        assert result is not None


class TestAuditLogDetailsSanitization:
    """The `details` dict should be JSON-serializable. Non-serializable
    values should be stringified, not crash."""

    async def test_complex_details_are_handled(self) -> None:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mix of serializable and non-serializable values
        await audit_log(
            mock_db,
            action=AuditAction.PII_ACCESSED,
            actor_id="user-1",
            details={
                "fields": ["aadhaar_hash", "bank_account"],
                "purpose": "claim_review",
                "count": 42,
                "nested": {"key": "value"},
                "object": object(),  # not JSON-serializable
            },
        )
        # If this didn't crash, sanitization worked

    async def test_none_actor_and_resource(self) -> None:
        """System-generated audit logs (e.g. erasure of a deleted user) have
        actor_id=None and possibly resource_id=None — must not crash."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        await audit_log(
            mock_db,
            action=AuditAction.DSR_ERASURE_APPLIED,
            actor_id=None,
            actor_role="system",
            resource_type="user",
            resource_id="deleted-user-uuid",
        )


class TestAuditLogPiiAccess:
    """Convenience wrapper for PII access audits."""

    async def test_pii_access_logs_with_fields_and_purpose(self) -> None:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        await audit_log_pii_access(
            mock_db,
            actor_id="officer-1",
            actor_role="agri_officer",
            resource_type="farmer_profile",
            resource_id="profile-1",
            fields_accessed=["aadhaar_hash", "bank_account_encrypted"],
            purpose="claim_review",
        )
        # Verify execute was called (i.e. the audit was attempted)
        assert mock_db.execute.called


class TestRequestContextExtraction:
    """When a Request is passed, IP/UA/request_id should be extracted."""

    async def test_extracts_headers_from_request(self) -> None:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mock a Request object
        mock_request = MagicMock()
        mock_request.headers = {
            "x-forwarded-for": "203.0.113.5, 10.0.0.1",
            "user-agent": "Mozilla/5.0 (Test Browser)",
        }
        mock_request.client = MagicMock(host="10.0.0.1")
        mock_request.state.request_id = "req-abc-123"

        await audit_log(
            mock_db,
            action=AuditAction.LOGIN_SUCCESS,
            actor_id="user-1",
            request=mock_request,
        )
        # Verify the params passed to execute() contain the extracted values
        call_args = mock_db.execute.call_args
        params = call_args.kwargs.get("params") or call_args.args[1]
        assert params["ip_address"] == "203.0.113.5"  # first X-Forwarded-For IP
        assert params["user_agent"] == "Mozilla/5.0 (Test Browser)"
        assert params["request_id"] == "req-abc-123"

    async def test_falls_back_to_client_ip_without_forwarded_for(self) -> None:
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_request = MagicMock()
        mock_request.headers = {}  # No X-Forwarded-For
        mock_request.client = MagicMock(host="192.168.1.1")
        mock_request.state.request_id = "req-xyz"

        await audit_log(
            mock_db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=None,
            request=mock_request,
        )
        call_args = mock_db.execute.call_args
        params = call_args.kwargs.get("params") or call_args.args[1]
        assert params["ip_address"] == "192.168.1.1"
