"""Integration tests for the consent domain (Phase F).

These tests exercise the consent lifecycle against a real database:
- grant_consent creates a Consent record with status=granted
- granting an already-granted purpose supersedes the old grant
- withdraw_consent marks the active grant as withdrawn
- has_active_consent returns the correct state
- get_consent_status returns granted/withdrawn/not_yet_asked sets

Requires:
- Postgres test DB (DATABASE_URL env var)
- alembic upgrade head has been run

If the DB is unavailable, the tests are skipped.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.consent.models import ConsentPurpose, ConsentStatus
from krishisetu.domains.consent.schemas import (
    ConsentGrantRequest,
    ConsentWithdrawRequest,
)
from krishisetu.domains.consent.services import (
    get_consent_status,
    grant_consent,
    has_active_consent,
    list_consent_history,
    withdraw_consent,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_id() -> str:
    """A random user_id for each test (no FK enforcement in tests)."""
    return str(uuid4())


class TestGrantConsent:
    async def test_grant_creates_record(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        payload = ConsentGrantRequest(
            purposes=[ConsentPurpose.DISEASE_DIAGNOSIS, ConsentPurpose.WEATHER_ADVISORY],
            notice_version="2026.07.01",
        )
        created = await grant_consent(db_session, user_id, payload)
        assert len(created) == 2
        for c in created:
            assert c.status == ConsentStatus.GRANTED.value
            assert c.notice_version == "2026.07.01"

    async def test_grant_supersedes_existing(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        """Re-granting the same purpose should supersede the old grant."""
        # First grant
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.NDVI_MONITORING]),
        )
        # Second grant for the same purpose
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.NDVI_MONITORING]),
        )
        # History should have 2 records: 1 withdrawn, 1 granted
        history = await list_consent_history(db_session, user_id)
        ndvi_records = [h for h in history if h.purpose == ConsentPurpose.NDVI_MONITORING.value]
        assert len(ndvi_records) == 2
        withdrawn = [r for r in ndvi_records if r.status == ConsentStatus.WITHDRAWN.value]
        granted = [r for r in ndvi_records if r.status == ConsentStatus.GRANTED.value]
        assert len(withdrawn) == 1
        assert len(granted) == 1
        assert withdrawn[0].withdrawal_reason == "superseded by new grant"


class TestWithdrawConsent:
    async def test_withdraw_marks_grant_as_withdrawn(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        # First grant
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.VOICE_PROCESSING]),
        )
        # Withdraw
        withdrawn = await withdraw_consent(
            db_session,
            user_id,
            ConsentWithdrawRequest(
                purposes=[ConsentPurpose.VOICE_PROCESSING],
                reason="user opted out",
            ),
        )
        assert len(withdrawn) == 1
        assert withdrawn[0].status == ConsentStatus.WITHDRAWN.value
        assert withdrawn[0].withdrawal_reason == "user opted out"

    async def test_withdraw_without_grant_is_idempotent(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        """Withdrawing a purpose that was never granted should be a no-op."""
        withdrawn = await withdraw_consent(
            db_session,
            user_id,
            ConsentWithdrawRequest(purposes=[ConsentPurpose.COMMUNICATION]),
        )
        assert withdrawn == []


class TestHasActiveConsent:
    async def test_returns_true_after_grant(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.INSURANCE_PROCESSING]),
        )
        assert await has_active_consent(
            db_session, user_id, ConsentPurpose.INSURANCE_PROCESSING
        ) is True

    async def test_returns_false_after_withdraw(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.INSURANCE_PROCESSING]),
        )
        await withdraw_consent(
            db_session,
            user_id,
            ConsentWithdrawRequest(purposes=[ConsentPurpose.INSURANCE_PROCESSING]),
        )
        assert await has_active_consent(
            db_session, user_id, ConsentPurpose.INSURANCE_PROCESSING
        ) is False

    async def test_returns_false_for_never_granted(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        assert await has_active_consent(
            db_session, user_id, ConsentPurpose.MARKETPLACE_TRANSACTIONS
        ) is False


class TestGetConsentStatus:
    async def test_categorizes_purposes_correctly(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        # Grant 2, withdraw 1, leave the rest unasked
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(
                purposes=[ConsentPurpose.DISEASE_DIAGNOSIS, ConsentPurpose.WEATHER_ADVISORY]
            ),
        )
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.COMMUNICATION]),
        )
        await withdraw_consent(
            db_session,
            user_id,
            ConsentWithdrawRequest(purposes=[ConsentPurpose.COMMUNICATION]),
        )

        status = await get_consent_status(db_session, user_id)
        assert ConsentPurpose.DISEASE_DIAGNOSIS in status.granted
        assert ConsentPurpose.WEATHER_ADVISORY in status.granted
        assert ConsentPurpose.COMMUNICATION in status.withdrawn
        assert ConsentPurpose.NDVI_MONITORING in status.not_yet_asked
        assert ConsentPurpose.IDENTITY_VERIFICATION in status.not_yet_asked

    async def test_empty_for_new_user(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        status = await get_consent_status(db_session, user_id)
        assert status.granted == []
        assert status.withdrawn == []
        assert len(status.not_yet_asked) == len(ConsentPurpose)


class TestListConsentHistory:
    async def test_returns_all_records_newest_first(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.DISEASE_DIAGNOSIS]),
        )
        await grant_consent(
            db_session,
            user_id,
            ConsentGrantRequest(purposes=[ConsentPurpose.WEATHER_ADVISORY]),
        )

        history = await list_consent_history(db_session, user_id)
        assert len(history) == 2
        # Newest first (Weather Advisory was granted second)
        assert history[0].purpose == ConsentPurpose.WEATHER_ADVISORY.value
        assert history[1].purpose == ConsentPurpose.DISEASE_DIAGNOSIS.value
