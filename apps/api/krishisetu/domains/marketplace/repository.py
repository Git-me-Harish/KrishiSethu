"""Database access layer for the marketplace domain."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.marketplace.models import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    Product,
    ProductCategory,
    Supplier,
)

# ---------------------------------------------------------------------------
# Category queries
# ---------------------------------------------------------------------------


async def list_categories(db: AsyncSession, *, is_active: bool = True) -> list[ProductCategory]:
    result = await db.execute(
        select(ProductCategory)
        .where(ProductCategory.is_active == is_active)
        .order_by(ProductCategory.sort_order, ProductCategory.name)
    )
    return list(result.scalars().all())


async def get_category_by_slug(db: AsyncSession, slug: str) -> ProductCategory | None:
    result = await db.execute(
        select(ProductCategory).where(ProductCategory.slug == slug)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Product queries
# ---------------------------------------------------------------------------


async def list_products(
    db: AsyncSession,
    *,
    category_slug: str | None = None,
    search: str | None = None,
    state: str | None = None,
    linked_disease_slug: str | None = None,
    is_in_stock: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List products with filters and pagination."""
    conditions = [Product.is_active.is_(True)]

    if category_slug:
        conditions.append(ProductCategory.slug == category_slug)

    if search:
        conditions.append(
            or_(
                Product.name.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%"),
                Product.brand.ilike(f"%{search}%"),
            )
        )

    if linked_disease_slug:
        conditions.append(Product.linked_disease_slug == linked_disease_slug)

    if is_in_stock is not None:
        conditions.append(Product.is_in_stock == is_in_stock)

    # Count
    count_query = (
        select(func.count(Product.id))
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .where(and_(*conditions))
    )
    if state:
        count_query = count_query.join(Supplier, Supplier.id == Product.supplier_id).where(
            and_(*conditions, Supplier.state == state)
        )
    total = (await db.execute(count_query)).scalar_one()

    # Data query with joins
    query = text("""
        SELECT p.*, s.business_name as supplier_name, c.name as category_name,
               c.slug as category_slug
        FROM commerce.products p
        JOIN commerce.suppliers s ON s.id = p.supplier_id
        JOIN commerce.product_categories c ON c.id = p.category_id
        WHERE p.is_active = true
    """)

    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    if category_slug:
        query = text(str(query) + " AND c.slug = :category_slug")
        params["category_slug"] = category_slug

    if search:
        query = text(
            str(query)
            + " AND (p.name ILIKE :search OR p.description ILIKE :search"
            + " OR p.brand ILIKE :search)"
        )
        params["search"] = f"%{search}%"

    if linked_disease_slug:
        query = text(str(query) + " AND p.linked_disease_slug = :disease_slug")
        params["disease_slug"] = linked_disease_slug

    if state:
        query = text(str(query) + " AND s.state = :state")
        params["state"] = state

    if is_in_stock is not None:
        if is_in_stock:
            query = text(str(query) + " AND p.is_in_stock = true")
        else:
            query = text(str(query) + " AND p.is_in_stock = false")

    query = text(str(query) + " ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset")

    result = await db.execute(query, params)
    products = [_row_to_product_dict(row) for row in result.fetchall()]
    return products, total


async def get_product_by_id(db: AsyncSession, product_id: UUID) -> dict[str, Any] | None:
    query = text("""
        SELECT p.*, s.business_name as supplier_name, c.name as category_name,
               c.slug as category_slug
        FROM commerce.products p
        JOIN commerce.suppliers s ON s.id = p.supplier_id
        JOIN commerce.product_categories c ON c.id = p.category_id
        WHERE p.id = :product_id AND p.is_active = true
    """)
    result = await db.execute(query, {"product_id": product_id})
    row = result.fetchone()
    return _row_to_product_dict(row) if row else None


async def get_products_by_disease(
    db: AsyncSession, disease_slug: str
) -> list[dict[str, Any]]:
    """Get products linked to a specific disease (for treatment recommendations)."""
    products, _ = await list_products(
        db, linked_disease_slug=disease_slug, page=1, page_size=20
    )
    return products


async def create_product(
    db: AsyncSession,
    *,
    supplier_id: UUID,
    category_id: UUID,
    name: str,
    description: str,
    price: Decimal,
    **kwargs,
) -> Product:
    """Create a new product."""
    import uuid as uuid_mod

    product = Product(
        id=uuid_mod.uuid4(),
        supplier_id=supplier_id,
        category_id=category_id,
        name=name,
        slug=name.lower().replace(" ", "-")[:200],
        description=description,
        price=price,
        **kwargs,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def update_product_stock(
    db: AsyncSession, product_id: UUID, quantity_change: int
) -> Product | None:
    """Update stock quantity (positive = add, negative = remove)."""
    product_result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = product_result.scalar_one_or_none()
    if not product:
        return None

    new_stock = product.stock_quantity + quantity_change
    await db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(
            stock_quantity=max(0, new_stock),
            is_in_stock=new_stock > 0,
            updated_at=datetime.now(UTC),
        )
    )
    await db.flush()
    result = await db.execute(select(Product).where(Product.id == product_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Supplier queries
# ---------------------------------------------------------------------------


async def get_supplier_by_user_id(db: AsyncSession, user_id: UUID) -> Supplier | None:
    result = await db.execute(
        select(Supplier).where(Supplier.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_supplier_by_id(db: AsyncSession, supplier_id: UUID) -> Supplier | None:
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Order queries
# ---------------------------------------------------------------------------


async def create_order(
    db: AsyncSession,
    *,
    order_number: str,
    farmer_id: UUID,
    subtotal: Decimal,
    shipping_cost: Decimal,
    total_amount: Decimal,
    shipping_name: str,
    shipping_phone: str,
    shipping_address_line1: str,
    shipping_address_line2: str | None,
    shipping_village: str | None,
    shipping_district: str,
    shipping_state: str,
    shipping_pincode: str,
    payment_method: str,
) -> Order:
    """Create a new order (status=placed, payment_status=pending)."""
    order = Order(
        order_number=order_number,
        farmer_id=farmer_id,
        status=OrderStatus.PLACED,
        payment_status=PaymentStatus.PENDING,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total_amount=total_amount,
        shipping_name=shipping_name,
        shipping_phone=shipping_phone,
        shipping_address_line1=shipping_address_line1,
        shipping_address_line2=shipping_address_line2,
        shipping_village=shipping_village,
        shipping_district=shipping_district,
        shipping_state=shipping_state,
        shipping_pincode=shipping_pincode,
        payment_method=payment_method,
        placed_at=datetime.now(UTC),
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)
    return order


async def create_order_item(
    db: AsyncSession,
    *,
    order_id: UUID,
    product_id: UUID,
    supplier_id: UUID,
    product_name: str,
    product_image_url: str | None,
    unit_price: Decimal,
    quantity: int,
    total_price: Decimal,
) -> OrderItem:
    """Create an order item."""
    item = OrderItem(
        order_id=order_id,
        product_id=product_id,
        supplier_id=supplier_id,
        product_name=product_name,
        product_image_url=product_image_url,
        unit_price=unit_price,
        quantity=quantity,
        total_price=total_price,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def get_order_by_id(
    db: AsyncSession, order_id: UUID, *, include_items: bool = True
) -> dict[str, Any] | None:
    """Get an order by ID with items."""
    query = text("""
        SELECT o.* FROM commerce.orders o WHERE o.id = :order_id
    """)
    result = await db.execute(query, {"order_id": order_id})
    row = result.fetchone()
    if not row:
        return None

    order_dict = _row_to_order_dict(row)

    if include_items:
        items_query = text("""
            SELECT oi.* FROM commerce.order_items oi
            WHERE oi.order_id = :order_id
            ORDER BY oi.created_at
        """)
        items_result = await db.execute(items_query, {"order_id": order_id})
        order_dict["items"] = [_row_to_order_item_dict(r) for r in items_result.fetchall()]
    else:
        order_dict["items"] = []

    return order_dict


async def list_orders_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: OrderStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's orders."""
    count_query = select(func.count(Order.id)).where(Order.farmer_id == farmer_id)
    if status:
        count_query = count_query.where(Order.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT o.* FROM commerce.orders o
        WHERE o.farmer_id = :farmer_id
        ORDER BY o.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params: dict[str, Any] = {"farmer_id": farmer_id, "limit": page_size, "offset": offset}
    if status:
        query = text(str(query).replace(
            "WHERE o.farmer_id = :farmer_id",
            "WHERE o.farmer_id = :farmer_id AND o.status = :status",
        ))
        params["status"] = status.value

    result = await db.execute(query, params)
    orders = []
    for row in result.fetchall():
        order_dict = _row_to_order_dict(row)
        # Fetch items
        items_query = text("""
            SELECT oi.* FROM commerce.order_items oi
            WHERE oi.order_id = :order_id
        """)
        items_result = await db.execute(items_query, {"order_id": order_dict["id"]})
        order_dict["items"] = [_row_to_order_item_dict(r) for r in items_result.fetchall()]
        orders.append(order_dict)

    return orders, total


async def list_orders_by_supplier(
    db: AsyncSession,
    supplier_id: UUID,
    *,
    status: OrderStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List orders containing products from a specific supplier."""
    count_query = (
        select(func.count(func.distinct(OrderItem.order_id)))
        .where(OrderItem.supplier_id == supplier_id)
    )
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT DISTINCT o.* FROM commerce.orders o
        JOIN commerce.order_items oi ON oi.order_id = o.id
        WHERE oi.supplier_id = :supplier_id
        ORDER BY o.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params: dict[str, Any] = {"supplier_id": supplier_id, "limit": page_size, "offset": offset}

    result = await db.execute(query, params)
    orders = []
    for row in result.fetchall():
        order_dict = _row_to_order_dict(row)
        items_query = text("""
            SELECT oi.* FROM commerce.order_items oi
            WHERE oi.order_id = :order_id AND oi.supplier_id = :supplier_id
        """)
        items_result = await db.execute(
            items_query, {"order_id": order_dict["id"], "supplier_id": supplier_id}
        )
        order_dict["items"] = [_row_to_order_item_dict(r) for r in items_result.fetchall()]
        orders.append(order_dict)

    return orders, total


async def update_order_status(
    db: AsyncSession,
    order_id: UUID,
    new_status: OrderStatus,
    *,
    cancelled_by: UUID | None = None,
    cancellation_reason: str | None = None,
    delivered_by: UUID | None = None,
) -> dict[str, Any] | None:
    """Update an order's status."""
    now = datetime.now(UTC)
    update_values: dict[str, Any] = {
        "status": new_status.value,
        "updated_at": now,
    }

    if new_status == OrderStatus.CANCELLED:
        update_values["cancelled_at"] = now
        update_values["cancelled_by"] = cancelled_by
        if cancellation_reason:
            update_values["cancellation_reason"] = cancellation_reason
    elif new_status == OrderStatus.DELIVERED:
        update_values["delivered_at"] = now
        update_values["delivery_confirmed_by"] = delivered_by

    await db.execute(
        update(Order).where(Order.id == order_id).values(**update_values)
    )
    await db.flush()
    return await get_order_by_id(db, order_id, include_items=True)


async def get_farmer_marketplace_stats(
    db: AsyncSession, farmer_id: UUID
) -> dict[str, Any]:
    """Get marketplace stats for a farmer."""
    query = text("""
        SELECT
            COUNT(*) as total_orders,
            COUNT(*) FILTER (
                WHERE status IN ('placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery')
            ) as pending_orders,
            COUNT(*) FILTER (WHERE status IN ('delivered', 'completed')) as completed_orders,
            COALESCE(SUM(total_amount), 0) as total_spent
        FROM commerce.orders
        WHERE farmer_id = :farmer_id
    """)
    result = await db.execute(query, {"farmer_id": farmer_id})
    row = result.fetchone()

    # Count distinct products ordered
    products_query = text("""
        SELECT COUNT(DISTINCT product_id) as total_products
        FROM commerce.order_items oi
        JOIN commerce.orders o ON o.id = oi.order_id
        WHERE o.farmer_id = :farmer_id
    """)
    products_result = await db.execute(products_query, {"farmer_id": farmer_id})
    products_row = products_result.fetchone()

    return {
        "total_products": products_row[0] or 0,
        "total_orders": row[0] or 0,
        "pending_orders": row[1] or 0,
        "completed_orders": row[2] or 0,
        "total_spent": Decimal(str(row[3] or 0)),
    }


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def _row_to_product_dict(row: Any) -> dict[str, Any]:
    """Convert a product row to a dict."""
    import json

    certifications = row.certifications
    if isinstance(certifications, str):
        try:
            certifications = json.loads(certifications)
        except Exception:
            certifications = None

    suitable_crops = row.suitable_crops
    if isinstance(suitable_crops, str):
        try:
            suitable_crops = json.loads(suitable_crops)
        except Exception:
            suitable_crops = None

    discount_pct = 0.0
    if row.mrp and row.mrp > 0 and row.price < row.mrp:
        discount_pct = float((row.mrp - row.price) / row.mrp * 100)

    return {
        "id": row.id,
        "supplier_id": row.supplier_id,
        "category_id": row.category_id,
        "name": row.name,
        "name_hi": getattr(row, "name_hi", None),
        "slug": row.slug,
        "description": row.description,
        "brand": getattr(row, "brand", None),
        "price": Decimal(str(row.price)),
        "mrp": Decimal(str(row.mrp)) if row.mrp else None,
        "unit": row.unit,
        "min_order_qty": row.min_order_qty,
        "stock_quantity": row.stock_quantity,
        "is_in_stock": row.is_in_stock,
        "image_url": getattr(row, "image_url", None),
        "certifications": certifications,
        "active_ingredient": getattr(row, "active_ingredient", None),
        "concentration": getattr(row, "concentration", None),
        "linked_disease_slug": getattr(row, "linked_disease_slug", None),
        "suitable_crops": suitable_crops,
        "rating": Decimal(str(row.rating)) if row.rating else Decimal("0"),
        "total_reviews": row.total_reviews,
        "discount_pct": round(discount_pct, 1),
        "supplier_name": getattr(row, "supplier_name", None),
        "category_name": getattr(row, "category_name", None),
    }


def _row_to_order_dict(row: Any) -> dict[str, Any]:
    """Convert an order row to a dict."""
    return {
        "id": row.id,
        "order_number": row.order_number,
        "farmer_id": row.farmer_id,
        "status": row.status,
        "payment_status": row.payment_status,
        "subtotal": Decimal(str(row.subtotal)),
        "shipping_cost": Decimal(str(row.shipping_cost)),
        "total_amount": Decimal(str(row.total_amount)),
        "shipping_name": row.shipping_name,
        "shipping_phone": row.shipping_phone,
        "shipping_address_line1": row.shipping_address_line1,
        "shipping_address_line2": getattr(row, "shipping_address_line2", None),
        "shipping_village": getattr(row, "shipping_village", None),
        "shipping_district": row.shipping_district,
        "shipping_state": row.shipping_state,
        "shipping_pincode": row.shipping_pincode,
        "placed_at": row.placed_at,
        "delivered_at": row.delivered_at,
        "created_at": row.created_at,
        "items": [],
    }


def _row_to_order_item_dict(row: Any) -> dict[str, Any]:
    """Convert an order item row to a dict."""
    return {
        "id": row.id,
        "product_id": row.product_id,
        "supplier_id": row.supplier_id,
        "product_name": row.product_name,
        "product_image_url": getattr(row, "product_image_url", None),
        "unit_price": Decimal(str(row.unit_price)),
        "quantity": row.quantity,
        "total_price": Decimal(str(row.total_price)),
        "fulfillment_status": row.fulfillment_status,
    }
