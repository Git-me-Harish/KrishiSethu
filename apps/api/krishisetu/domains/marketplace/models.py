"""SQLAlchemy ORM models for the marketplace domain.

Tables:
- commerce.product_categories   (seeds, fertilizers, pesticides, machinery, tools)
- commerce.suppliers            (verified vendors with license info)
- commerce.products             (catalog with images, pricing, certifications)
- commerce.orders               (farmer orders with state machine)
- commerce.order_items          (line items per order)
- commerce.shipments            (delivery tracking)

Design notes:
- Suppliers must have valid licenses (seed license, fertilizer license, GST)
  verified by admin before activation
- Products link to disease treatments (cross-module: disease → marketplace)
- Orders have a state machine: draft → placed → confirmed → packed →
  shipped → out_for_delivery → delivered → completed (or cancelled/returned)
- Inventory is tracked per-product with low-stock alerts
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProductCategoryType(str, Enum):
    """Type of agricultural input product."""

    SEEDS = "seeds"
    FERTILIZERS = "fertilizers"
    PESTICIDES = "pesticides"
    FUNGICIDES = "fungicides"
    HERBICIDES = "herbicides"
    MACHINERY = "machinery"
    TOOLS = "tools"
    IRRIGATION = "irrigation"
    ORGANIC_INPUTS = "organic_inputs"
    OTHER = "other"


class SupplierStatus(str, Enum):
    """Verification status of a supplier."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class OrderStatus(str, Enum):
    """Order lifecycle states.

    State transitions:
    - draft → placed (farmer checks out)
    - placed → confirmed (supplier accepts)
    - placed → cancelled (supplier rejects or farmer cancels)
    - confirmed → packed (supplier packs)
    - packed → shipped (supplier ships with tracking)
    - shipped → out_for_delivery (courier out for delivery)
    - out_for_delivery → delivered (farmer confirms receipt)
    - out_for_delivery → delivery_failed (courier returns)
    - delivered → completed (7-day return window expires)
    - delivered → returned (farmer returns within 7 days)
    - confirmed/packed/shipped → cancelled (farmer cancels, with conditions)
    """

    DRAFT = "draft"
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUND_INITIATED = "refund_initiated"


class PaymentStatus(str, Enum):
    """Payment status for an order."""

    PENDING = "pending"
    PAID = "paid"
    ESCROW_HELD = "escrow_held"
    RELEASED_TO_SUPPLIER = "released_to_supplier"
    REFUNDED = "refunded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# ProductCategory (master data)
# ---------------------------------------------------------------------------


class ProductCategory(Base):
    """Product category (seeds, fertilizers, pesticides, etc.).

    Categories are hierarchical — a category can have a parent.
    Example: seeds → cereal_seeds → rice_seeds
    """

    __tablename__ = "product_categories"
    __table_args__ = {"schema": "commerce"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_hi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.product_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    category_type: Mapped[ProductCategoryType] = mapped_column(
        String(30), nullable=False, index=True,
    )
    icon: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Icon name from lucide-react"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False, default=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, server_default=func.text("0"), nullable=False, default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")
    children: Mapped[list["ProductCategory"]] = relationship(
        "ProductCategory", backref="parent", remote_side="ProductCategory.id"
    )

    def __repr__(self) -> str:
        return f"<ProductCategory slug={self.slug} name={self.name}>"


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------


class Supplier(Base):
    """A verified agricultural input supplier.

    Linked to a user account (role=supplier). Suppliers must upload their
    licenses (seed license, fertilizer license, GST certificate) which are
    verified by an admin before the supplier can list products.
    """

    __tablename__ = "suppliers"
    __table_args__ = {"schema": "commerce"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_name_hi: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Contact
    phone: Mapped[str] = mapped_column(String(15), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # Address
    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    village: Mapped[str | None] = mapped_column(String(255), nullable=True)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pincode: Mapped[str] = mapped_column(String(10), nullable=False)

    # Licenses (S3 keys for uploaded documents)
    seed_license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seed_license_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fertilizer_license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fertilizer_license_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gst_certificate_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Verification
    status: Mapped[SupplierStatus] = mapped_column(
        String(20),
        server_default=func.text("'pending'"),
        nullable=False,
        default=SupplierStatus.PENDING,
        index=True,
    )
    verified_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rating (computed from order reviews)
    rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), server_default=func.text("0"), nullable=False, default=Decimal("0"),
    )
    total_ratings: Mapped[int] = mapped_column(
        Integer, server_default=func.text("0"), nullable=False, default=0,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship(
        "Product", back_populates="supplier", cascade="all, delete-orphan"
    )

    @property
    def is_verified(self) -> bool:
        return self.status == SupplierStatus.VERIFIED

    def __repr__(self) -> str:
        return f"<Supplier business={self.business_name} status={self.status}>"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


class Product(Base):
    """A product listed by a supplier.

    Products can be linked to disease treatments (cross-module integration):
    when a disease is identified, the platform can recommend specific products
    from the marketplace.

    Inventory is tracked per-product. When stock reaches low_stock_threshold,
    the supplier gets a notification.
    """

    __tablename__ = "products"
    __table_args__ = {"schema": "commerce"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.product_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Product details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_hi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Pricing
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mrp: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Maximum Retail Price (for discount display)",
    )
    unit: Mapped[str] = mapped_column(
        String(20), nullable=False, default="piece",
        comment="piece, kg, litre, packet, bag, etc.",
    )
    min_order_qty: Mapped[int] = mapped_column(
        Integer, server_default=func.text("1"), nullable=False, default=1,
    )

    # Inventory
    stock_quantity: Mapped[int] = mapped_column(
        Integer, server_default=func.text("0"), nullable=False, default=0,
    )
    low_stock_threshold: Mapped[int] = mapped_column(
        Integer, server_default=func.text("10"), nullable=False, default=10,
    )
    is_in_stock: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False, default=True,
    )

    # Images
    image_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="Primary image S3 key",
    )
    additional_images: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, comment="Array of S3 keys for additional images",
    )

    # Certifications
    certifications: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True,
        comment='["ISI", "Organic Certified", "CIB Registered"]',
    )
    active_ingredient: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="For pesticides/fungicides: active ingredient name",
    )
    concentration: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="For pesticides: e.g., '75% WP', '5% EC'",
    )

    # Cross-module link (disease → product)
    linked_disease_slug: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
        comment="If this product is a treatment for a specific disease",
    )

    # Crop suitability
    suitable_crops: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True,
        comment='["rice", "wheat", "cotton"] — crop slugs',
    )

    # Rating
    rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), server_default=func.text("0"), nullable=False, default=Decimal("0"),
    )
    total_reviews: Mapped[int] = mapped_column(
        Integer, server_default=func.text("0"), nullable=False, default=0,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False, default=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="products")
    category: Mapped[ProductCategory] = relationship("ProductCategory", back_populates="products")
    order_items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="product"
    )

    @property
    def discount_pct(self) -> float:
        """Discount percentage based on MRP vs price."""
        if self.mrp and self.mrp > 0 and self.price < self.mrp:
            return float((self.mrp - self.price) / self.mrp * 100)
        return 0.0

    def __repr__(self) -> str:
        return f"<Product name={self.name} price={self.price}>"


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


class Order(Base):
    """An order placed by a farmer.

    The order state machine transitions are enforced at the service layer.
    Payment is held in escrow until delivery confirmation, then released
    to the supplier.
    """

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("order_number", name="orders_order_number_unique"),
        {"schema": "commerce"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    order_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Order details
    status: Mapped[OrderStatus] = mapped_column(
        String(30),
        server_default=func.text("'draft'"),
        nullable=False,
        default=OrderStatus.DRAFT,
        index=True,
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        String(30),
        server_default=func.text("'pending'"),
        nullable=False,
        default=PaymentStatus.PENDING,
    )

    # Totals
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), server_default=func.text("0"), nullable=False, default=Decimal("0"),
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Shipping address
    shipping_name: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(15), nullable=False)
    shipping_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_village: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_district: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(100), nullable=False)
    shipping_pincode: Mapped[str] = mapped_column(String(10), nullable=False)

    # Payment
    payment_method: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="upi, razorpay, cod",
    )
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Cancellation
    cancelled_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Delivery
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    delivery_confirmed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
    )

    # Timestamps
    placed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    shipments: Mapped[list["Shipment"]] = relationship(
        "Shipment", back_populates="order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Order number={self.order_number} status={self.status}>"


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------


class OrderItem(Base):
    """A line item in an order.

    Stores a snapshot of the product at order time (name, price) so that
    later changes to the product catalog don't affect historical orders.
    """

    __tablename__ = "order_items"
    __table_args__ = {"schema": "commerce"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Snapshot (at order time)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Fulfillment
    fulfillment_status: Mapped[str] = mapped_column(
        String(30),
        server_default=func.text("'pending'"),
        nullable=False,
        default="pending",
        comment="pending, confirmed, packed, shipped, delivered",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    order: Mapped[Order] = relationship("Order", back_populates="items")
    product: Mapped[Product] = relationship("Product", back_populates="order_items")

    def __repr__(self) -> str:
        return f"<OrderItem product={self.product_name} qty={self.quantity}>"


# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------


class Shipment(Base):
    """Shipment tracking for an order.

    An order may have multiple shipments (split shipment from different
    suppliers). Each shipment has its own tracking number and carrier.
    """

    __tablename__ = "shipments"
    __table_args__ = {"schema": "commerce"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Shipment details
    tracking_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    carrier: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="DTDC, BlueDart, India Post, etc.",
    )
    tracking_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(30),
        server_default=func.text("'pending'"),
        nullable=False,
        default="pending",
        comment="pending, shipped, in_transit, out_for_delivery, delivered, returned",
    )

    # Timestamps
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Items in this shipment (JSONB array of order_item IDs)
    item_ids: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True,
        comment="Array of order_item UUIDs in this shipment",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationship
    order: Mapped[Order] = relationship("Order", back_populates="shipments")

    def __repr__(self) -> str:
        return f"<Shipment order={self.order_id} tracking={self.tracking_number}>"
