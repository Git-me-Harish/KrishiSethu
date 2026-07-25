"""Pydantic schemas for the marketplace domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductCategoryTypeEnum(str, Enum):
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


class SupplierStatusEnum(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class OrderStatusEnum(str, Enum):
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


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    ESCROW_HELD = "escrow_held"
    RELEASED_TO_SUPPLIER = "released_to_supplier"
    REFUNDED = "refunded"
    FAILED = "failed"


# Product Category
class ProductCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    name_hi: str | None
    category_type: str
    icon: str | None
    sort_order: int


class ProductCategoryListResponse(BaseModel):
    categories: list[ProductCategoryResponse]
    total: int


# Product
class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    supplier_id: UUID
    category_id: UUID
    name: str
    name_hi: str | None
    slug: str
    description: str
    brand: str | None
    price: Decimal
    mrp: Decimal | None
    unit: str
    min_order_qty: int
    stock_quantity: int
    is_in_stock: bool
    image_url: str | None
    certifications: list[str] | None
    active_ingredient: str | None
    concentration: str | None
    linked_disease_slug: str | None
    suitable_crops: list[str] | None
    rating: Decimal
    total_reviews: int
    discount_pct: float = 0.0
    supplier_name: str | None = None
    category_name: str | None = None


class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class ProductCreate(BaseModel):
    category_id: UUID
    name: str = Field(..., min_length=2, max_length=255)
    name_hi: str | None = None
    description: str = Field(..., min_length=10, max_length=5000)
    brand: str | None = None
    price: Decimal = Field(..., gt=0)
    mrp: Decimal | None = None
    unit: str = "piece"
    min_order_qty: int = Field(default=1, ge=1)
    stock_quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=10, ge=0)
    image_url: str | None = None
    certifications: list[str] | None = None
    active_ingredient: str | None = None
    concentration: str | None = None
    linked_disease_slug: str | None = None
    suitable_crops: list[str] | None = None


# Cart
class CartItem(BaseModel):
    product_id: UUID
    quantity: int = Field(..., ge=1)


class CartResponse(BaseModel):
    items: list[CartItem]
    total: Decimal
    total_items: int


# Order
class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    product_name: str
    product_image_url: str | None
    unit_price: Decimal
    quantity: int
    total_price: Decimal
    fulfillment_status: str


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    order_number: str
    farmer_id: UUID
    status: OrderStatusEnum
    payment_status: PaymentStatusEnum
    subtotal: Decimal
    shipping_cost: Decimal
    total_amount: Decimal
    shipping_name: str
    shipping_phone: str
    shipping_address_line1: str
    shipping_address_line2: str | None
    shipping_village: str | None
    shipping_district: str
    shipping_state: str
    shipping_pincode: str
    placed_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class OrderCreateRequest(BaseModel):
    items: list[CartItem] = Field(..., min_length=1)
    shipping_name: str = Field(..., min_length=2, max_length=255)
    shipping_phone: str = Field(..., min_length=10, max_length=15)
    shipping_address_line1: str = Field(..., min_length=5, max_length=255)
    shipping_address_line2: str | None = None
    shipping_village: str | None = None
    shipping_district: str = Field(..., min_length=1, max_length=100)
    shipping_state: str = Field(..., min_length=1, max_length=100)
    shipping_pincode: str = Field(..., pattern=r"^[1-9][0-9]{5}$")
    payment_method: str = Field(default="upi", description="upi, razorpay, cod")


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., description="confirm, pack, ship, deliver, cancel")
    tracking_number: str | None = None
    carrier: str | None = None


class MarketplaceStatsResponse(BaseModel):
    total_products: int
    total_orders: int
    pending_orders: int
    completed_orders: int
    total_spent: Decimal
