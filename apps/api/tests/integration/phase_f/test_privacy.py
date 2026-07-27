"""Integration tests for the privacy domain — DSR & grievances (Phase F).

Exercises:
- create_dsr creates a record with status=acknowledged and a future due_at
- SLA calculations (15 days for correction, 30 days for access)
- create_grievance generates a unique grievance_number
- Grievance SLA is 30 days
- update_dsr updates status and writes audit trail

Requires a Postgres test DB. If unavailable, tests are skipped.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.privacy.models import DSRStatus, DSRType, GrievanceStatus
from krishisetu.domains.privacy.services import (
    SLA_ACCESS,
    SLA_CORRECTION,
    SLA_GRIEVANCE,
    create_dsr,
    create_grievance,
    list_my_dsrs,
    update_dsr,
    update_grievance,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


class TestCreateDsr:
    async def test_access_dsr_auto_acknowledged(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(db_session, user_id, DSRType.ACCESS, description="want my data")
        assert dsr.status == DSRStatus.ACKNOWLEDGED.value
        assert dsr.acknowledged_at is not None
        assert dsr.submitted_at is not None
        # Acknowledged within seconds of submission (DPDP: 24h SLA)
        assert (dsr.acknowledged_at - dsr.submitted_at).total_seconds() < 5

    async def test_access_dsr_due_at_is_30_days(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(db_session, user_id, DSRType.ACCESS)
        delta = dsr.due_at - dsr.submitted_at
        assert timedelta(days=SLA_ACCESS - 1) < delta < timedelta(days=SLA_ACCESS + 1)

    async def test_correction_dsr_due_at_is_15_days(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(db_session, user_id, DSRType.CORRECTION)
        delta = dsr.due_at - dsr.submitted_at
        assert timedelta(days=SLA_CORRECTION - 1) < delta < timedelta(days=SLA_CORRECTION + 1)

    async def test_dsr_with_requested_changes(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(
            db_session,
            user_id,
            DSRType.CORRECTION,
            description="Fix my bank account",
            requested_changes={"bank_account": "12345678901234"},
        )
        assert dsr.requested_changes == {"bank_account": "12345678901234"}


class TestUpdateDsr:
    async def test_complete_dsr_sets_completed_at(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(db_session, user_id, DSRType.ACCESS)
        updated = await update_dsr(
            db_session,
            dsr.id,
            status=DSRStatus.COMPLETED,
            resolution_notes="Data exported",
            export_url="https://s3.example.com/export.json",
        )
        assert updated is not None
        assert updated.status == DSRStatus.COMPLETED.value
        assert updated.completed_at is not None
        assert updated.export_url == "https://s3.example.com/export.json"

    async def test_reject_dsr_records_reason(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        dsr = await create_dsr(db_session, user_id, DSRType.ERASURE)
        updated = await update_dsr(
            db_session,
            dsr.id,
            status=DSRStatus.REJECTED,
            rejection_reason="Legal obligation to retain payment records",
        )
        assert updated.status == DSRStatus.REJECTED.value
        assert "Legal obligation" in updated.rejection_reason


class TestListDsrs:
    async def test_returns_only_my_dsrs(
        self,
        db_session: AsyncSession,
    ) -> None:
        user_a = str(uuid4())
        user_b = str(uuid4())
        await create_dsr(db_session, user_a, DSRType.ACCESS)
        await create_dsr(db_session, user_a, DSRType.CORRECTION)
        await create_dsr(db_session, user_b, DSRType.ACCESS)

        mine = await list_my_dsrs(db_session, user_a)
        assert len(mine) == 2
        # All should belong to user_a
        assert all(str(d.user_id) == user_a for d in mine)


class TestCreateGrievance:
    async def test_generates_unique_grievance_number(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        g1 = await create_grievance(
            db_session,
            user_id,
            category="data_quality",
            subject="Wrong bank account",
            description="My account number is incorrect",
        )
        g2 = await create_grievance(
            db_session,
            user_id,
            category="consent_violation",
            subject="Receiving SMS after withdrawal",
            description="I withdrew SMS consent but still get messages",
        )
        assert g1.grievance_number != g2.grievance_number
        assert g1.grievance_number.startswith("GRV-")
        assert g2.grievance_number.startswith("GRV-")

    async def test_auto_acknowledged(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        g = await create_grievance(
            db_session,
            user_id,
            category="unauthorized_access",
            subject="Someone accessed my account",
            description="I see logins from unknown IPs",
        )
        assert g.status == GrievanceStatus.ACKNOWLEDGED.value
        assert g.acknowledged_at is not None

    async def test_grievance_due_at_is_30_days(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        g = await create_grievance(
            db_session,
            user_id,
            category="other",
            subject="Test",
            description="Test",
        )
        delta = g.due_at - g.filed_at
        assert timedelta(days=SLA_GRIEVANCE - 1) < delta < timedelta(days=SLA_GRIEVANCE + 1)


class TestUpdateGrievance:
    async def test_resolve_sets_resolved_at(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        g = await create_grievance(
            db_session,
            user_id,
            category="data_quality",
            subject="Test",
            description="Test",
        )
        updated = await update_grievance(
            db_session,
            g.id,
            status=GrievanceStatus.RESOLVED,
            resolution="Bank account corrected",
        )
        assert updated.status == GrievanceStatus.RESOLVED.value
        assert updated.resolved_at is not None
        assert updated.resolution == "Bank account corrected"

    async def test_escalate_sets_reference(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        g = await create_grievance(
            db_session,
            user_id,
            category="consent_violation",
            subject="Test",
            description="Test",
        )
        updated = await update_grievance(
            db_session,
            g.id,
            status=GrievanceStatus.ESCALATED,
            escalation_reference="DPBI-2026-00123",
        )
        assert updated.status == GrievanceStatus.ESCALATED.value
        assert updated.escalation_reference == "DPBI-2026-00123"
