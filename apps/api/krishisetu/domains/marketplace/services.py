"""Marketplace service — business logic for products, orders, and fulfillment."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import NotFoundError, ValidationError
from krishisetu.core.logging import get_logger
from krishisetu.domains.marketplace import repository as repo
from krishisetu.domains.marketplace.models import OrderStatus
from krishisetu.domains.marketplace.schemas import (
    MarketplaceStatsResponse,
    OrderCreateRequest,
    OrderListResponse,
    OrderResponse,
    OrderStatusUpdate,
    ProductCategoryListResponse,
    ProductCategoryResponse,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
)

logger = get_logger(__name__)

# Free shipping threshold
FREE_SHIPPING_THRESHOLD = Decimal("2000")
SHIPPING_COST = Decimal("50")


# ---------------------------------------------------------------------------
# Category services
# ---------------------------------------------------------------------------


async def list_categories(db: AsyncSession) -> ProductCategoryListResponse:
    cats = await repo.list_categories(db)
    return ProductCategoryListResponse(
        categories=[ProductCategoryResponse.model_validate(c) for c in cats],
        total=len(cats),
    )


# ---------------------------------------------------------------------------
# Product services
# ---------------------------------------------------------------------------


async def list_products(
    db: AsyncSession,
    *,
    category: str | None = None,
    search: str | None = None,
    state: str | None = None,
    disease_slug: str | None = None,
    in_stock: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ProductListResponse:
    products, total = await repo.list_products(
        db,
        category_slug=category,
        search=search,
        state=state,
        linked_disease_slug=disease_slug,
        is_in_stock=in_stock,
        page=page,
        page_size=page_size,
    )
    return ProductListResponse(
        products=[ProductResponse(**p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def get_product(db: AsyncSession, product_id: UUID) -> ProductResponse:
    product = await repo.get_product_by_id(db, product_id)
    if not product:
        raise NotFoundError("Product", str(product_id))
    return ProductResponse(**product)


async def get_products_for_disease(
    db: AsyncSession, disease_slug: str
) -> list[ProductResponse]:
    """Get products linked to a disease (for treatment recommendations)."""
    products = await repo.get_products_by_disease(db, disease_slug)
    return [ProductResponse(**p) for p in products]


async def create_product(
    db: AsyncSession,
    supplier_user_id: UUID,
    payload: ProductCreate,
) -> ProductResponse:
    """Supplier creates a new product."""
    supplier = await repo.get_supplier_by_user_id(db, supplier_user_id)
    if not supplier:
        raise NotFoundError("Supplier", "No supplier profile found for this user")

    if not supplier.is_verified:
        raise ValidationError(
            "Supplier account is not verified. Cannot list products until verified."
        )

    product = await repo.create_product(
        db,
        supplier_id=supplier.id,
        category_id=payload.category_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        name_hi=payload.name_hi,
        brand=payload.brand,
        mrp=payload.mrp,
        unit=payload.unit,
        min_order_qty=payload.min_order_qty,
        stock_quantity=payload.stock_quantity,
        low_stock_threshold=payload.low_stock_threshold,
        image_url=payload.image_url,
        certifications=payload.certifications,
        active_ingredient=payload.active_ingredient,
        concentration=payload.concentration,
        linked_disease_slug=payload.linked_disease_slug,
        suitable_crops=payload.suitable_crops,
    )

    product_dict = await repo.get_product_by_id(db, product.id)
    if product_dict:
        return ProductResponse(**product_dict)
    return ProductResponse.model_validate(product)


# ---------------------------------------------------------------------------
# Order services
# ---------------------------------------------------------------------------


async def place_order(
    db: AsyncSession,
    farmer_id: UUID,
    payload: OrderCreateRequest,
) -> OrderResponse:
    """Place a new order.

    Steps:
    1. Validate all products exist and are in stock
    2. Compute subtotal from current prices
    3. Compute shipping cost
    4. Create order with status=placed
    5. Create order items (with price snapshot)
    6. Decrement stock quantities
    """
    # Validate and compute totals
    items_data = []
    subtotal = Decimal("0")

    for item in payload.items:
        product = await repo.get_product_by_id(db, item.product_id)
        if not product:
            raise NotFoundError("Product", str(item.product_id))

        if not product["is_in_stock"]:
            raise ValidationError(f"Product '{product['name']}' is out of stock")

        if product["stock_quantity"] < item.quantity:
            raise ValidationError(
                f"Insufficient stock for '{product['name']}'. "
                f"Available: {product['stock_quantity']}, requested: {item.quantity}"
            )

        if item.quantity < product["min_order_qty"]:
            raise ValidationError(
                f"Minimum order quantity for '{product['name']}' is {product['min_order_qty']}"
            )

        unit_price = product["price"]
        total_price = unit_price * item.quantity
        subtotal += total_price

        items_data.append({
            "product": product,
            "quantity": item.quantity,
            "unit_price": unit_price,
            "total_price": total_price,
        })

    # Shipping cost
    shipping_cost = Decimal("0") if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_COST
    total_amount = subtotal + shipping_cost

    # Generate order number
    order_number = _generate_order_number()

    # Create order
    order = await repo.create_order(
        db,
        order_number=order_number,
        farmer_id=farmer_id,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total_amount=total_amount,
        shipping_name=payload.shipping_name,
        shipping_phone=payload.shipping_phone,
        shipping_address_line1=payload.shipping_address_line1,
        shipping_address_line2=payload.shipping_address_line2,
        shipping_village=payload.shipping_village,
        shipping_district=payload.shipping_district,
        shipping_state=payload.shipping_state,
        shipping_pincode=payload.shipping_pincode,
        payment_method=payload.payment_method,
    )

    # Create order items and decrement stock
    for item_data in items_data:
        product = item_data["product"]
        await repo.create_order_item(
            db,
            order_id=order.id,
            product_id=item_data["product"]["id"],
            supplier_id=item_data["product"]["supplier_id"],
            product_name=item_data["product"]["name"],
            product_image_url=item_data["product"].get("image_url"),
            unit_price=item_data["unit_price"],
            quantity=item_data["quantity"],
            total_price=item_data["total_price"],
        )

        # Decrement stock
        await repo.update_product_stock(
            db, item_data["product"]["id"], -item_data["quantity"]
        )

    logger.info(
        "marketplace.order_placed",
        order_id=str(order.id),
        order_number=order_number,
        farmer_id=str(farmer_id),
        total_amount=str(total_amount),
        items_count=len(items_data),
    )

    order_dict = await repo.get_order_by_id(db, order.id, include_items=True)
    return OrderResponse(**order_dict)


async def list_my_orders(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: OrderStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> OrderListResponse:
    orders, total = await repo.list_orders_by_farmer(
        db, farmer_id, status=status, page=page, page_size=page_size
    )
    return OrderListResponse(
        orders=[OrderResponse(**o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def get_order(
    db: AsyncSession,
    order_id: UUID,
    farmer_id: UUID,
) -> OrderResponse:
    order_dict = await repo.get_order_by_id(db, order_id, include_items=True)
    if not order_dict:
        raise NotFoundError("Order", str(order_id))

    if order_dict["farmer_id"] != farmer_id:
        raise NotFoundError("Order", str(order_id))

    return OrderResponse(**order_dict)


async def cancel_order(
    db: AsyncSession,
    order_id: UUID,
    farmer_id: UUID,
    reason: str | None = None,
) -> OrderResponse:
    """Farmer cancels an order (only if not yet shipped)."""
    order_dict = await repo.get_order_by_id(db, order_id, include_items=False)
    if not order_dict:
        raise NotFoundError("Order", str(order_id))

    if order_dict["farmer_id"] != farmer_id:
        raise NotFoundError("Order", str(order_id))

    if order_dict["status"] not in (
        OrderStatus.PLACED.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.PACKED.value,
    ):
        raise ValidationError(
            f"Cannot cancel order in '{order_dict['status']}' state. "
            f"Only placed/confirmed/packed orders can be cancelled."
        )

    # Restore stock
    order_with_items = await repo.get_order_by_id(db, order_id, include_items=True)
    for item in order_with_items.get("items", []):
        await repo.update_product_stock(db, item["product_id"], item["quantity"])

    updated = await repo.update_order_status(
        db,
        order_id,
        OrderStatus.CANCELLED,
        cancelled_by=farmer_id,
        cancellation_reason=reason,
    )
    return OrderResponse(**updated)


# ---------------------------------------------------------------------------
# Supplier order management
# ---------------------------------------------------------------------------


async def supplier_list_orders(
    db: AsyncSession,
    supplier_user_id: UUID,
    *,
    status: OrderStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> OrderListResponse:
    supplier = await repo.get_supplier_by_user_id(db, supplier_user_id)
    if not supplier:
        raise NotFoundError("Supplier", "No supplier profile found")

    orders, total = await repo.list_orders_by_supplier(
        db, supplier.id, status=status, page=page, page_size=page_size
    )
    return OrderListResponse(
        orders=[OrderResponse(**o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def supplier_update_order_status(
    db: AsyncSession,
    order_id: UUID,
    supplier_user_id: UUID,
    payload: OrderStatusUpdate,
) -> OrderResponse:
    """Supplier updates order status (confirm, pack, ship, deliver)."""
    supplier = await repo.get_supplier_by_user_id(db, supplier_user_id)
    if not supplier:
        raise NotFoundError("Supplier", "No supplier profile found")

    order_dict = await repo.get_order_by_id(db, order_id, include_items=True)
    if not order_dict:
        raise NotFoundError("Order", str(order_id))

    # Verify this supplier has items in this order
    has_items = any(
        item.get("supplier_id") == supplier.id
        for item in order_dict.get("items", [])
    )
    if not has_items:
        raise NotFoundError("Order", str(order_id))

    # Map action to status
    action_to_status = {
        "confirm": OrderStatus.CONFIRMED,
        "pack": OrderStatus.PACKED,
        "ship": OrderStatus.SHIPPED,
        "deliver": OrderStatus.DELIVERED,
        "cancel": OrderStatus.CANCELLED,
    }

    if payload.status not in action_to_status:
        raise ValidationError(
            f"Invalid status update: '{payload.status}'. "
            f"Must be one of: {', '.join(action_to_status.keys())}"
        )

    new_status = action_to_status[payload.status]

    # Validate state transition
    current_status = order_dict["status"]
    valid_transitions = {
        OrderStatus.PLACED: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.CONFIRMED: [OrderStatus.PACKED, OrderStatus.CANCELLED],
        OrderStatus.PACKED: [OrderStatus.SHIPPED],
        OrderStatus.SHIPPED: [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED],
        OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED, OrderStatus.DELIVERY_FAILED],
    }

    allowed = valid_transitions.get(OrderStatus(current_status), [])
    if new_status not in allowed:
        raise ValidationError(
            f"Cannot transition from '{current_status}' to '{new_status.value}'"
        )

    updated = await repo.update_order_status(
        db,
        order_id,
        new_status,
        cancelled_by=supplier_user_id if new_status == OrderStatus.CANCELLED else None,
    )

    # Create shipment record if shipping
    if new_status == OrderStatus.SHIPPED and payload.tracking_number:
        from krishisetu.domains.marketplace.models import Shipment

        shipment = Shipment(
            order_id=order_id,
            supplier_id=supplier.id,
            tracking_number=payload.tracking_number,
            carrier=payload.carrier,
            shipped_at=datetime.now(UTC),
            status="shipped",
        )
        db.add(shipment)
        await db.flush()

    logger.info(
        "marketplace.order_status_updated",
        order_id=str(order_id),
        new_status=new_status.value,
        supplier_id=str(supplier.id),
    )

    return OrderResponse(**updated)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_marketplace_stats(
    db: AsyncSession, farmer_id: UUID
) -> MarketplaceStatsResponse:
    stats = await repo.get_farmer_marketplace_stats(db, farmer_id)
    return MarketplaceStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_order_number() -> str:
    """Generate unique order number: KS-ORD-YYYYMMDD-8hex"""
    today = datetime.now(UTC).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"KS-ORD-{today}-{short_uuid}"
