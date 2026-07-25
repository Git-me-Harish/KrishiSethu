"""Marketplace routes.

Endpoints:
Public (no auth):
- GET /marketplace/products          — Browse products (search, filter)
- GET /marketplace/products/{id}     — Product detail
- GET /marketplace/categories        — List product categories
- GET /marketplace/diseases/{slug}/products — Products for a disease

Farmer (require auth):
- POST /marketplace/orders           — Place an order
- GET  /marketplace/orders           — List own orders
- GET  /marketplace/orders/{id}      — Get order detail
- POST /marketplace/orders/{id}/cancel — Cancel an order
- GET  /marketplace/stats            — Marketplace stats

Supplier (require auth + supplier role):
- POST /supplier/products            — Create a product
- GET  /supplier/orders              — List supplier's orders
- PATCH /supplier/orders/{id}/status — Update order status (confirm, pack, ship, deliver)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import (
    PERM_MARKETPLACE_BROWSE,
    PERM_MARKETPLACE_ORDER,
    PERM_MARKETPLACE_READ_OWN_ORDERS,
    PERM_SUPPLIER_CATALOG_MANAGE,
    PERM_SUPPLIER_ORDER_FULFILL,
)
from krishisetu.domains.marketplace import services
from krishisetu.domains.marketplace.models import OrderStatus
from krishisetu.domains.marketplace.schemas import (
    MarketplaceStatsResponse,
    OrderCreateRequest,
    OrderListResponse,
    OrderResponse,
    OrderStatusUpdate,
    ProductCategoryListResponse,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

marketplace_router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@marketplace_router.get("/categories", response_model=ProductCategoryListResponse)
async def list_categories(db: DBSession) -> ProductCategoryListResponse:
    """List all product categories (public)."""
    return await services.list_categories(db)


@marketplace_router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: DBSession,
    category: str | None = Query(default=None, description="Category slug"),
    search: str | None = Query(default=None, description="Search term"),
    state: str | None = Query(default=None, description="Filter by supplier state"),
    disease: str | None = Query(default=None, description="Filter by linked disease slug"),
    in_stock: bool | None = Query(default=None, description="Only in-stock products"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ProductListResponse:
    """Browse marketplace products (public — no auth required)."""
    return await services.list_products(
        db,
        category=category,
        search=search,
        state=state,
        disease_slug=disease,
        in_stock=in_stock,
        page=page,
        page_size=page_size,
    )


@marketplace_router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: Annotated[UUID, Path()],
    db: DBSession,
) -> ProductResponse:
    """Get product detail (public)."""
    return await services.get_product(db, product_id)


@marketplace_router.get(
    "/diseases/{disease_slug}/products",
    response_model=list[ProductResponse],
)
async def get_products_for_disease(
    disease_slug: Annotated[str, Path()],
    db: DBSession,
) -> list[ProductResponse]:
    """Get products linked to a disease (for treatment recommendations).

    Public endpoint — used by the disease result page to show
    "Order Treatment" options.
    """
    return await services.get_products_for_disease(db, disease_slug)


# ---------------------------------------------------------------------------
# Farmer order routes
# ---------------------------------------------------------------------------

@marketplace_router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_ORDER))],
)
async def place_order(
    payload: OrderCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> OrderResponse:
    """Place a new order.

    The order is created with status=placed and payment_status=pending.
    Stock is decremented immediately. If the order is cancelled, stock is restored.

    Shipping is free for orders above ₹2,000, otherwise ₹50 flat rate.
    """
    return await services.place_order(db, current_user.id, payload)


@marketplace_router.get(
    "/orders",
    response_model=OrderListResponse,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_READ_OWN_ORDERS))],
)
async def list_my_orders(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: OrderStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> OrderListResponse:
    """List the farmer's orders."""
    return await services.list_my_orders(
        db, current_user.id, status=status_filter, page=page, page_size=page_size
    )


@marketplace_router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_READ_OWN_ORDERS))],
)
async def get_order(
    order_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> OrderResponse:
    """Get order detail with items."""
    return await services.get_order(db, order_id, current_user.id)


@marketplace_router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderResponse,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_ORDER))],
)
async def cancel_order(
    order_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    reason: str | None = Query(default=None, description="Cancellation reason"),
) -> OrderResponse:
    """Cancel an order (only if not yet shipped).

    Stock is restored when the order is cancelled.
    """
    return await services.cancel_order(db, order_id, current_user.id, reason=reason)


@marketplace_router.get(
    "/stats",
    response_model=MarketplaceStatsResponse,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_READ_OWN_ORDERS))],
)
async def get_marketplace_stats(
    current_user: CurrentUser,
    db: DBSession,
) -> MarketplaceStatsResponse:
    """Get marketplace stats for the farmer."""
    return await services.get_marketplace_stats(db, current_user.id)


# ---------------------------------------------------------------------------
# Supplier routes
# ---------------------------------------------------------------------------

supplier_router = APIRouter(
    prefix="/supplier",
    tags=["supplier"],
)


@supplier_router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_SUPPLIER_CATALOG_MANAGE))],
)
async def create_product(
    payload: ProductCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> ProductResponse:
    """Supplier creates a new product listing.

    Requires a verified supplier account.
    """
    return await services.create_product(db, current_user.id, payload)


@supplier_router.get(
    "/orders",
    response_model=OrderListResponse,
    dependencies=[Depends(require_permissions(PERM_SUPPLIER_ORDER_FULFILL))],
)
async def supplier_list_orders(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: OrderStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> OrderListResponse:
    """List orders containing this supplier's products."""
    return await services.supplier_list_orders(
        db, current_user.id, status=status_filter, page=page, page_size=page_size
    )


@supplier_router.patch(
    "/orders/{order_id}/status",
    response_model=OrderResponse,
    dependencies=[Depends(require_permissions(PERM_SUPPLIER_ORDER_FULFILL))],
)
async def supplier_update_order_status(
    order_id: Annotated[UUID, Path()],
    payload: OrderStatusUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> OrderResponse:
    """Supplier updates order status (confirm, pack, ship, deliver).

    State transitions:
    - placed → confirmed (supplier accepts)
    - confirmed → packed (supplier packs)
    - packed → shipped (supplier ships with tracking)
    - shipped → delivered (courier delivers)
    """
    return await services.supplier_update_order_status(
        db, order_id, current_user.id, payload
    )
