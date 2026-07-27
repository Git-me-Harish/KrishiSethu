"""Database access layer for the farmer domain.

Handles PostGIS-specific operations:
- Converting GeoJSON to WKT/WKB for storage
- Computing area from polygon (ST_Area)
- Spatial overlap detection (ST_Intersects)
- District-scoped queries for officers

GeoJSON conversion:
- Frontend sends GeoJSON Polygon
- We convert to WKT (Well-Known Text) using shapely
- PostGIS stores as GEOGRAPHY(POLYGON, 4326)
- On read, we convert back to GeoJSON via ST_AsGeoJSON()
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.farmer.models import (
    Crop,
    CropCycle,
    CropCycleStatus,
    CropSeason,
    IrrigationSource,
    Plot,
    PlotBoundary,
    PlotOwnershipType,
    PlotVerificationStatus,
)


# ---------------------------------------------------------------------------
# Helpers: GeoJSON <-> WKT conversion
# ---------------------------------------------------------------------------


def geojson_to_wkt(geojson: dict[str, Any]) -> str:
    """Convert GeoJSON Polygon dict to WKT (Well-Known Text).

    Example:
        Input: {"type": "Polygon", "coordinates": [[[72.8, 19.1], [72.81, 19.1], ...]]}
        Output: "POLYGON((72.8 19.1, 72.81 19.1, ...))"

    For polygons with holes, output is:
        "POLYGON((exterior_ring), (hole1), (hole2))"
    """
    if geojson.get("type") != "Polygon":
        raise ValueError(f"Expected GeoJSON Polygon, got {geojson.get('type')}")

    rings = geojson.get("coordinates", [])
    if not rings:
        raise ValueError("Polygon must have at least one ring")

    # Format each ring as "lon lat, lon lat, ..."
    ring_wkts = []
    for ring in rings:
        coords_str = ", ".join(f"{lon} {lat}" for lon, lat, *_ in ring)
        ring_wkts.append(f"({coords_str})")

    rings_str = ", ".join(ring_wkts)
    return f"SRID=4326;POLYGON({rings_str})"


def wkt_to_geojson(wkt_or_geojson: Any) -> dict[str, Any] | None:
    """Convert a PostGIS geometry to GeoJSON dict.

    Accepts either:
    - A GeoJSON dict (already converted by ST_AsGeoJSON)
    - A WKT string
    - A geoalchemy2 element

    Returns None if input is None.
    """
    if wkt_or_geojson is None:
        return None

    # If it's already a dict (from ST_AsGeoJSON), return as-is
    if isinstance(wkt_or_geojson, dict):
        return wkt_or_geojson

    # If it's a string, try parsing as JSON (ST_AsGeoJSON returns JSON text)
    if isinstance(wkt_or_geojson, str):
        try:
            return json.loads(wkt_or_geojson)
        except json.JSONDecodeError:
            # It's WKT — convert manually (basic implementation)
            return _wkt_to_geojson(wkt_or_geojson)

    # geoalchemy2 WKBElement — would need shapely for full conversion
    # In our queries, we always use ST_AsGeoJSON so we don't hit this path
    return None


def _wkt_to_geojson(wkt: str) -> dict[str, Any]:
    """Parse a simple WKT POLYGON string to GeoJSON. Basic implementation."""
    # Strip SRID prefix if present
    if wkt.startswith("SRID="):
        wkt = wkt.split(";", 1)[1]

    if not wkt.startswith("POLYGON"):
        raise ValueError(f"Unsupported WKT type: {wkt[:20]}")

    # Extract content between outer parens
    start = wkt.index("(") + 1
    end = wkt.rindex(")")
    content = wkt[start:end]

    # Split into rings (each ring is in parens)
    rings = []
    depth = 0
    current = ""
    for char in content:
        if char == "(":
            depth += 1
            if depth == 1:
                current = ""
                continue
        elif char == ")":
            depth -= 1
            if depth == 0:
                rings.append(current.strip())
                continue
        if depth >= 1:
            current += char

    # Parse each ring into coordinate pairs
    geojson_rings = []
    for ring in rings:
        coords = []
        for pair in ring.split(","):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split()
            lon = float(parts[0])
            lat = float(parts[1])
            coords.append([lon, lat])
        geojson_rings.append(coords)

    return {"type": "Polygon", "coordinates": geojson_rings}


# ---------------------------------------------------------------------------
# Crop queries (master data)
# ---------------------------------------------------------------------------


async def list_crops(
    db: AsyncSession,
    *,
    category: str | None = None,
    season: CropSeason | None = None,
    is_active: bool = True,
) -> list[Crop]:
    """List all crops, optionally filtered by category and season."""
    query = select(Crop).where(Crop.is_active == is_active)
    if category:
        query = query.where(Crop.crop_category == category)
    if season:
        query = query.where(Crop.primary_season == season)
    query = query.order_by(Crop.crop_category, Crop.name_en)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_crop_by_id(db: AsyncSession, crop_id: UUID) -> Crop | None:
    """Fetch a crop by ID."""
    result = await db.execute(select(Crop).where(Crop.id == crop_id))
    return result.scalar_one_or_none()


async def get_crop_by_slug(db: AsyncSession, slug: str) -> Crop | None:
    """Fetch a crop by slug."""
    result = await db.execute(select(Crop).where(Crop.slug == slug))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Plot queries
# ---------------------------------------------------------------------------


async def create_plot(
    db: AsyncSession,
    *,
    farmer_id: UUID,
    survey_number: str,
    village: str,
    district: str,
    state: str,
    boundary_geojson: dict[str, Any],
    pincode: str | None = None,
    irrigation_source: IrrigationSource | None = None,
    ownership_type: PlotOwnershipType = PlotOwnershipType.OWNED,
    lessor_name: str | None = None,
    lease_start_date=None,
    lease_end_date=None,
    nickname: str | None = None,
    soil_type: str | None = None,
    soil_ph: Decimal | None = None,
) -> tuple[Plot, Decimal]:
    """Create a new plot.

    The boundary is provided as GeoJSON dict and converted to WKT for storage.
    The area is computed in the database via ST_Area() and returned alongside
    the plot.

    Returns (plot, area_ha).
    """
    # Convert GeoJSON to WKT with SRID
    boundary_wkt = geojson_to_wkt(boundary_geojson)

    # Insert using raw SQL to leverage PostGIS functions for area computation
    # We use ST_GeogFromText to create geography from WKT
    # ST_Area on geography returns area in square meters; divide by 10000 for hectares
    query = text("""
        INSERT INTO farmer.plots
            (farmer_id, survey_number, village, district, state, pincode,
             area_ha, boundary, irrigation_source, ownership_type,
             lessor_name, lease_start_date, lease_end_date, nickname,
             soil_type, soil_ph)
        VALUES
            (:farmer_id, :survey_number, :village, :district, :state, :pincode,
             ST_Area(ST_GeogFromText(:boundary)) / 10000.0,
             ST_GeogFromText(:boundary),
             :irrigation_source, :ownership_type,
             :lessor_name, :lease_start_date, :lease_end_date, :nickname,
             :soil_type, :soil_ph)
        RETURNING id, farmer_id, survey_number, village, district, state, pincode,
                  area_ha, ST_AsGeoJSON(boundary) as boundary_geojson,
                  ST_AsGeoJSON(centroid) as centroid_geojson,
                  soil_type, soil_ph, irrigation_source, ownership_type,
                  lessor_name, lease_start_date, lease_end_date,
                  verification_status, verified_by, verified_at, verification_notes,
                  nickname, created_at, updated_at
    """)

    result = await db.execute(
        query,
        {
            "farmer_id": farmer_id,
            "survey_number": survey_number,
            "village": village,
            "district": district,
            "state": state,
            "pincode": pincode,
            "boundary": boundary_wkt,
            "irrigation_source": irrigation_source.value if irrigation_source else None,
            "ownership_type": ownership_type.value,
            "lessor_name": lessor_name,
            "lease_start_date": lease_start_date,
            "lease_end_date": lease_end_date,
            "nickname": nickname,
            "soil_type": soil_type,
            "soil_ph": float(soil_ph) if soil_ph else None,
        },
    )
    row = result.fetchone()
    await db.flush()

    # Convert row to Plot-like dict (we'll use a typed dict in the service layer)
    plot_dict = _row_to_plot_dict(row)
    area_ha = plot_dict["area_ha"]

    # Also archive the boundary in plot_boundaries
    await create_boundary_snapshot(
        db,
        plot_id=plot_dict["id"],
        boundary_geojson=boundary_geojson,
        area_ha=area_ha,
        source="user_drawn",
        created_by=farmer_id,
    )

    # Re-fetch as ORM object for consistency
    plot = await get_plot_by_id(db, plot_dict["id"])
    return plot, area_ha


async def get_plot_by_id(
    db: AsyncSession, plot_id: UUID, *, include_boundary: bool = True
) -> Plot | None:
    """Fetch a plot by ID with boundary as GeoJSON."""
    if include_boundary:
        # Use raw SQL to get ST_AsGeoJSON
        query = text("""
            SELECT id, farmer_id, survey_number, village, district, state, pincode,
                   area_ha, ST_AsGeoJSON(boundary) as boundary_geojson,
                   ST_AsGeoJSON(centroid) as centroid_geojson,
                   soil_type, soil_ph, irrigation_source, ownership_type,
                   lessor_name, lease_start_date, lease_end_date,
                   verification_status, verified_by, verified_at, verification_notes,
                   nickname, created_at, updated_at
            FROM farmer.plots
            WHERE id = :plot_id
        """)
        result = await db.execute(query, {"plot_id": plot_id})
        row = result.fetchone()
        if not row:
            return None
        return _row_to_plot_obj(row)
    else:
        result = await db.execute(select(Plot).where(Plot.id == plot_id))
        return result.scalar_one_or_none()


async def get_plot_with_centroid(db: AsyncSession, plot_id: UUID) -> dict[str, Any] | None:
    """Get plot with centroid as {lon, lat} dict (for proximity queries)."""
    query = text("""
        SELECT id, farmer_id, survey_number, village, district, state,
               area_ha, verification_status, nickname,
               ST_X(centroid::geometry) as centroid_lon,
               ST_Y(centroid::geometry) as centroid_lat,
               ST_AsGeoJSON(boundary) as boundary_geojson,
               ST_AsGeoJSON(centroid) as centroid_geojson,
               soil_type, soil_ph, irrigation_source, ownership_type,
               lessor_name, lease_start_date, lease_end_date,
               verified_by, verified_at, verification_notes, pincode,
               created_at, updated_at
        FROM farmer.plots
        WHERE id = :plot_id
    """)
    result = await db.execute(query, {"plot_id": plot_id})
    row = result.fetchone()
    if not row:
        return None
    return _row_to_plot_dict(row)


async def list_plots_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's plots with centroid (no full boundary for list view).

    Returns (plots, total_count).
    """
    offset = (page - 1) * page_size

    # Count query
    count_query = select(func.count(Plot.id)).where(Plot.farmer_id == farmer_id)
    total = (await db.execute(count_query)).scalar_one()

    # Data query with centroid
    query = text("""
        SELECT p.id, p.survey_number, p.village, p.district, p.state,
               p.area_ha, p.verification_status, p.nickname,
               ST_X(p.centroid::geometry) as centroid_lon,
               ST_Y(p.centroid::geometry) as centroid_lat,
               p.created_at,
               (SELECT c.name_en FROM farmer.crop_cycles cc
                JOIN farmer.crops c ON c.id = cc.crop_id
                WHERE cc.plot_id = p.id AND cc.status IN ('sown', 'growing')
                ORDER BY cc.created_at DESC LIMIT 1) as current_crop,
               (SELECT cc.id FROM farmer.crop_cycles cc
                WHERE cc.plot_id = p.id AND cc.status IN ('sown', 'growing')
                ORDER BY cc.created_at DESC LIMIT 1) as current_crop_cycle_id
        FROM farmer.plots p
        WHERE p.farmer_id = :farmer_id
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(
        query,
        {"farmer_id": farmer_id, "limit": page_size, "offset": offset},
    )
    rows = result.fetchall()
    plots = [_row_to_list_item_dict(row) for row in rows]
    return plots, total


async def farmer_has_plot_in_district(
    db: AsyncSession,
    farmer_id: UUID,
    district: str,
    state: str,
) -> bool:
    """Whether a farmer holds any plot in the given district.

    Used to scope officer actions on farmer-owned records (scheme
    applications, disease reports) to the officer's own district.
    """
    result = await db.execute(
        select(func.count(Plot.id)).where(
            Plot.farmer_id == farmer_id,
            Plot.district == district,
            Plot.state == state,
        )
    )
    return result.scalar_one() > 0


async def list_plots_by_district(
    db: AsyncSession,
    district: str | None,
    state: str | None = None,
    *,
    verification_status: PlotVerificationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List plots in a district (for agri officers).

    `district`/`state` of None mean unrestricted — only ever passed for admin
    callers. The same filters are applied to the count and the page so an
    officer's worklist cannot leak plots outside their district.
    """
    offset = (page - 1) * page_size

    count_query = select(func.count(Plot.id))
    if district:
        count_query = count_query.where(Plot.district == district)
    if state:
        count_query = count_query.where(Plot.state == state)
    if verification_status:
        count_query = count_query.where(Plot.verification_status == verification_status)
    total = (await db.execute(count_query)).scalar_one()

    params: dict[str, Any] = {"limit": page_size, "offset": offset}
    filters = ["1 = 1"]
    if district:
        filters.append("p.district = :district")
        params["district"] = district
    if state:
        filters.append("p.state = :state")
        params["state"] = state
    if verification_status:
        filters.append("p.verification_status = :verification_status")
        params["verification_status"] = verification_status.value

    query = text(f"""
        SELECT p.id, p.survey_number, p.village, p.district, p.state,
               p.area_ha, p.verification_status, p.nickname,
               ST_X(p.centroid::geometry) as centroid_lon,
               ST_Y(p.centroid::geometry) as centroid_lat,
               p.created_at,
               u.full_name as farmer_name,
               u.phone as farmer_phone
        FROM farmer.plots p
        JOIN identity.users u ON u.id = p.farmer_id
        WHERE {' AND '.join(filters)}
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(query, params)
    rows = result.fetchall()
    plots = [_row_to_list_item_dict(row) for row in rows]
    return plots, total


async def update_plot(
    db: AsyncSession,
    plot_id: UUID,
    **fields: object,
) -> Plot | None:
    """Update editable fields on a plot (not boundary — use update_boundary)."""
    if not fields:
        return await get_plot_by_id(db, plot_id, include_boundary=False)

    # Allowlist of updatable fields
    allowed = {"nickname", "irrigation_source", "pincode"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_plot_by_id(db, plot_id, include_boundary=False)

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    params = {"plot_id": plot_id, **updates}
    query = text(f"""
        UPDATE farmer.plots
        SET {set_clauses}, updated_at = NOW()
        WHERE id = :plot_id
    """)
    await db.execute(query, params)
    await db.flush()
    return await get_plot_by_id(db, plot_id)


async def update_plot_boundary(
    db: AsyncSession,
    plot_id: UUID,
    boundary_geojson: dict[str, Any],
    source: str = "user_drawn",
    updated_by: UUID | None = None,
) -> tuple[Plot, Decimal] | None:
    """Update a plot's boundary.

    Archives the old boundary in plot_boundaries before updating.
    Recomputes area_ha from the new boundary.
    """
    # Get current plot to archive its boundary
    current = await get_plot_by_id(db, plot_id)
    if not current:
        return None

    # Archive old boundary
    if current.boundary:
        await create_boundary_snapshot(
            db,
            plot_id=plot_id,
            boundary_geojson=current.boundary
            if isinstance(current.boundary, dict)
            else {"type": "Polygon", "coordinates": []},
            area_ha=current.area_ha,
            source="pre_update",
            created_by=updated_by,
        )

    # Update with new boundary
    boundary_wkt = geojson_to_wkt(boundary_geojson)
    query = text("""
        UPDATE farmer.plots
        SET boundary = ST_GeogFromText(:boundary),
            area_ha = ST_Area(ST_GeogFromText(:boundary)) / 10000.0,
            updated_at = NOW()
        WHERE id = :plot_id
        RETURNING id
    """)
    await db.execute(query, {"plot_id": plot_id, "boundary": boundary_wkt})
    await db.flush()

    # Get updated plot
    updated_plot = await get_plot_by_id(db, plot_id)
    if not updated_plot:
        return None

    # Archive new boundary
    await create_boundary_snapshot(
        db,
        plot_id=plot_id,
        boundary_geojson=boundary_geojson,
        area_ha=updated_plot.area_ha,
        source=source,
        created_by=updated_by,
    )

    return updated_plot, updated_plot.area_ha


async def delete_plot(db: AsyncSession, plot_id: UUID) -> bool:
    """Soft delete by hard-deleting the row (cascade removes related records).

    For audit compliance, we keep historical records via plot_boundaries and
    audit_log. The plot row itself is deleted to free up the unique constraint
    (survey_number + village + district) for re-registration if needed.
    """
    result = await db.execute(
        delete(Plot).where(Plot.id == plot_id)
    )
    await db.flush()
    return result.rowcount > 0


async def check_plot_overlap(
    db: AsyncSession,
    boundary_geojson: dict[str, Any],
    exclude_plot_id: UUID | None = None,
) -> list[UUID]:
    """Check if the given boundary overlaps any existing plot.

    Used to warn farmers when their drawn boundary overlaps another plot
    (potential duplicate registration or boundary dispute).

    Returns list of overlapping plot IDs (empty if no overlaps).
    """
    boundary_wkt = geojson_to_wkt(boundary_geojson)
    query = text("""
        SELECT id FROM farmer.plots
        WHERE ST_Intersects(boundary, ST_GeogFromText(:boundary))
    """)
    params: dict[str, Any] = {"boundary": boundary_wkt}
    if exclude_plot_id:
        query += " AND id != :exclude_id"
        params["exclude_id"] = exclude_plot_id
    result = await db.execute(query, params)
    return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# Plot boundary history
# ---------------------------------------------------------------------------


async def create_boundary_snapshot(
    db: AsyncSession,
    *,
    plot_id: UUID,
    boundary_geojson: dict[str, Any],
    area_ha: Decimal,
    source: str = "user_drawn",
    created_by: UUID | None = None,
) -> PlotBoundary | None:
    """Archive a boundary snapshot in plot_boundaries."""
    boundary_wkt = geojson_to_wkt(boundary_geojson)
    query = text("""
        INSERT INTO farmer.plot_boundaries
            (plot_id, boundary, area_ha, source, created_by)
        VALUES
            (:plot_id, ST_GeogFromText(:boundary), :area_ha, :source, :created_by)
        RETURNING id
    """)
    result = await db.execute(
        query,
        {
            "plot_id": plot_id,
            "boundary": boundary_wkt,
            "area_ha": float(area_ha),
            "source": source,
            "created_by": created_by,
        },
    )
    await db.flush()
    row = result.fetchone()
    return row[0] if row else None


async def list_boundary_history(
    db: AsyncSession, plot_id: UUID
) -> list[PlotBoundary]:
    """List all historical boundary snapshots for a plot."""
    result = await db.execute(
        select(PlotBoundary)
        .where(PlotBoundary.plot_id == plot_id)
        .order_by(PlotBoundary.created_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Officer verification
# ---------------------------------------------------------------------------


async def verify_plot(
    db: AsyncSession,
    plot_id: UUID,
    officer_id: UUID,
    status: PlotVerificationStatus,
    notes: str | None = None,
) -> Plot | None:
    """Update a plot's verification status."""
    await db.execute(
        update(Plot)
        .where(Plot.id == plot_id)
        .values(
            verification_status=status.value,
            verified_by=officer_id,
            verified_at=datetime.utcnow(),
            verification_notes=notes,
        )
    )
    await db.flush()
    return await get_plot_by_id(db, plot_id, include_boundary=False)


# ---------------------------------------------------------------------------
# Plot statistics
# ---------------------------------------------------------------------------


async def get_plot_stats(db: AsyncSession, farmer_id: UUID) -> dict[str, Any]:
    """Get summary statistics for a farmer's plots."""
    query = text("""
        SELECT
            COUNT(*) as total_plots,
            COALESCE(SUM(area_ha), 0) as total_area_ha,
            COUNT(*) FILTER (WHERE verification_status = 'verified') as verified_plots,
            COUNT(*) FILTER (WHERE verification_status = 'pending') as pending_verification,
            COUNT(*) FILTER (WHERE verification_status = 'rejected') as rejected_plots,
            COUNT(*) FILTER (WHERE ownership_type = 'leased') as leased_plots
        FROM farmer.plots
        WHERE farmer_id = :farmer_id
    """)
    result = await db.execute(query, {"farmer_id": farmer_id})
    row = result.fetchone()

    # District breakdown
    district_query = text("""
        SELECT district, COUNT(*) as count
        FROM farmer.plots
        WHERE farmer_id = :farmer_id
        GROUP BY district
    """)
    district_result = await db.execute(district_query, {"farmer_id": farmer_id})
    by_district = {row[0]: row[1] for row in district_result.fetchall()}

    # Current crops (sown or growing)
    crop_query = text("""
        SELECT c.name_en
        FROM farmer.crop_cycles cc
        JOIN farmer.crops c ON c.id = cc.crop_id
        JOIN farmer.plots p ON p.id = cc.plot_id
        WHERE p.farmer_id = :farmer_id AND cc.status IN ('sown', 'growing')
    """)
    crop_result = await db.execute(crop_query, {"farmer_id": farmer_id})
    current_crops = [row[0] for row in crop_result.fetchall()]

    return {
        "total_plots": row[0] or 0,
        "total_area_ha": Decimal(str(row[1] or 0)),
        "verified_plots": row[2] or 0,
        "pending_verification": row[3] or 0,
        "rejected_plots": row[4] or 0,
        "leased_plots": row[5] or 0,
        "by_district": by_district,
        "current_season_crops": current_crops,
    }


# ---------------------------------------------------------------------------
# Crop cycle queries
# ---------------------------------------------------------------------------


async def create_crop_cycle(
    db: AsyncSession,
    *,
    plot_id: UUID,
    crop_id: UUID,
    season: CropSeason,
    season_year: int,
    area_ha: Decimal,
    sowing_date=None,
    expected_harvest_date=None,
    notes: str | None = None,
) -> CropCycle:
    """Create a new crop cycle on a plot."""
    cycle = CropCycle(
        plot_id=plot_id,
        crop_id=crop_id,
        season=season,
        season_year=season_year,
        area_ha=area_ha,
        sowing_date=sowing_date,
        expected_harvest_date=expected_harvest_date,
        notes=notes,
    )
    db.add(cycle)
    await db.flush()
    await db.refresh(cycle)
    return cycle


async def get_crop_cycle_by_id(db: AsyncSession, cycle_id: UUID) -> dict[str, Any] | None:
    """Get a crop cycle with crop name joined."""
    query = text("""
        SELECT cc.id, cc.plot_id, cc.crop_id, c.name_en as crop_name,
               cc.season, cc.season_year,
               cc.sowing_date, cc.expected_harvest_date, cc.actual_harvest_date,
               cc.area_ha, cc.status, cc.notes, cc.created_at, cc.updated_at
        FROM farmer.crop_cycles cc
        JOIN farmer.crops c ON c.id = cc.crop_id
        WHERE cc.id = :cycle_id
    """)
    result = await db.execute(query, {"cycle_id": cycle_id})
    row = result.fetchone()
    if not row:
        return None
    return _row_to_crop_cycle_dict(row)


async def list_crop_cycles_by_plot(
    db: AsyncSession, plot_id: UUID
) -> list[dict[str, Any]]:
    """List all crop cycles for a plot, most recent first."""
    query = text("""
        SELECT cc.id, cc.plot_id, cc.crop_id, c.name_en as crop_name,
               cc.season, cc.season_year,
               cc.sowing_date, cc.expected_harvest_date, cc.actual_harvest_date,
               cc.area_ha, cc.status, cc.notes, cc.created_at, cc.updated_at
        FROM farmer.crop_cycles cc
        JOIN farmer.crops c ON c.id = cc.crop_id
        WHERE cc.plot_id = :plot_id
        ORDER BY cc.season_year DESC, cc.created_at DESC
    """)
    result = await db.execute(query, {"plot_id": plot_id})
    return [_row_to_crop_cycle_dict(row) for row in result.fetchall()]


async def update_crop_cycle(
    db: AsyncSession,
    cycle_id: UUID,
    **fields: object,
) -> dict[str, Any] | None:
    """Update a crop cycle."""
    allowed = {
        "sowing_date",
        "expected_harvest_date",
        "actual_harvest_date",
        "status",
        "notes",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_crop_cycle_by_id(db, cycle_id)

    # Convert status enum to value
    if "status" in updates and hasattr(updates["status"], "value"):
        updates["status"] = updates["status"].value

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    query = text(f"""
        UPDATE farmer.crop_cycles
        SET {set_clauses}, updated_at = NOW()
        WHERE id = :cycle_id
    """)
    await db.execute(query, {"cycle_id": cycle_id, **updates})
    await db.flush()
    return await get_crop_cycle_by_id(db, cycle_id)


async def check_active_crop_cycle(
    db: AsyncSession, plot_id: UUID
) -> bool:
    """Check if a plot has any active (sown or growing) crop cycle."""
    query = text("""
        SELECT EXISTS(
            SELECT 1 FROM farmer.crop_cycles
            WHERE plot_id = :plot_id AND status IN ('sown', 'growing')
        )
    """)
    result = await db.execute(query, {"plot_id": plot_id})
    return result.scalar()


# ---------------------------------------------------------------------------
# Row mappers (private)
# ---------------------------------------------------------------------------


def _row_to_plot_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy row to a plot dict with parsed GeoJSON."""
    boundary_geojson = None
    if hasattr(row, "boundary_geojson") and row.boundary_geojson:
        try:
            boundary_geojson = (
                json.loads(row.boundary_geojson)
                if isinstance(row.boundary_geojson, str)
                else row.boundary_geojson
            )
        except (json.JSONDecodeError, TypeError):
            pass

    centroid = None
    if hasattr(row, "centroid_geojson") and row.centroid_geojson:
        try:
            centroid_data = (
                json.loads(row.centroid_geojson)
                if isinstance(row.centroid_geojson, str)
                else row.centroid_geojson
            )
            if centroid_data and "coordinates" in centroid_data:
                centroid = {
                    "lon": centroid_data["coordinates"][0],
                    "lat": centroid_data["coordinates"][1],
                }
        except (json.JSONDecodeError, TypeError, IndexError):
            pass
    elif hasattr(row, "centroid_lon") and row.centroid_lon is not None:
        centroid = {"lon": float(row.centroid_lon), "lat": float(row.centroid_lat)}

    return {
        "id": row.id,
        "farmer_id": row.farmer_id,
        "survey_number": row.survey_number,
        "village": row.village,
        "district": row.district,
        "state": row.state,
        "pincode": row.pincode,
        "area_ha": Decimal(str(row.area_ha)),
        "boundary": boundary_geojson,
        "centroid": centroid,
        "soil_type": row.soil_type,
        "soil_ph": Decimal(str(row.soil_ph)) if row.soil_ph else None,
        "irrigation_source": row.irrigation_source,
        "ownership_type": row.ownership_type,
        "lessor_name": getattr(row, "lessor_name", None),
        "lease_start_date": getattr(row, "lease_start_date", None),
        "lease_end_date": getattr(row, "lease_end_date", None),
        "verification_status": row.verification_status,
        "verified_by": getattr(row, "verified_by", None),
        "verified_at": getattr(row, "verified_at", None),
        "verification_notes": getattr(row, "verification_notes", None),
        "nickname": getattr(row, "nickname", None),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _row_to_plot_obj(row: Any) -> Plot:
    """Convert a row to a Plot ORM-like object (with parsed boundary dict)."""
    plot_dict = _row_to_plot_dict(row)
    plot = Plot.__new__(Plot)
    for k, v in plot_dict.items():
        setattr(plot, k, v)
    return plot


def _row_to_list_item_dict(row: Any) -> dict[str, Any]:
    """Convert a row to a list-item dict (no boundary, just centroid)."""
    centroid = None
    if hasattr(row, "centroid_lon") and row.centroid_lon is not None:
        centroid = {"lon": float(row.centroid_lon), "lat": float(row.centroid_lat)}

    return {
        "id": row.id,
        "survey_number": row.survey_number,
        "village": row.village,
        "district": row.district,
        "state": row.state,
        "area_ha": Decimal(str(row.area_ha)),
        "verification_status": row.verification_status,
        "nickname": getattr(row, "nickname", None),
        "centroid": centroid,
        "current_crop": getattr(row, "current_crop", None),
        "current_crop_cycle_id": getattr(row, "current_crop_cycle_id", None),
        "created_at": row.created_at,
        "farmer_name": getattr(row, "farmer_name", None),
        "farmer_phone": getattr(row, "farmer_phone", None),
    }


def _row_to_crop_cycle_dict(row: Any) -> dict[str, Any]:
    """Convert a row to a crop cycle dict."""
    return {
        "id": row.id,
        "plot_id": row.plot_id,
        "crop_id": row.crop_id,
        "crop_name": row.crop_name,
        "season": row.season,
        "season_year": row.season_year,
        "sowing_date": row.sowing_date,
        "expected_harvest_date": row.expected_harvest_date,
        "actual_harvest_date": row.actual_harvest_date,
        "area_ha": Decimal(str(row.area_ha)),
        "status": row.status,
        "notes": row.notes,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
