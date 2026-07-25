"""Create marketplace schema: categories, suppliers, products, orders, order_items, shipments

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS commerce;")

    # --- product_categories ---
    op.create_table(
        "product_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_hi", sa.String(100), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category_type", sa.String(30), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "category_type IN ('seeds', 'fertilizers', 'pesticides', 'fungicides', 'herbicides', 'machinery', 'tools', 'irrigation', 'organic_inputs', 'other')",
            name="product_categories_type_check",
        ),
        sa.UniqueConstraint("slug", name="product_categories_slug_unique"),
        sa.ForeignKeyConstraint(["parent_id"], ["commerce.product_categories.id"], ondelete="SET NULL", name="product_categories_parent_fk"),
        schema="commerce",
    )
    op.create_index("idx_prod_cat_slug", "product_categories", ["slug"], schema="commerce")
    op.create_index("idx_prod_cat_type", "product_categories", ["category_type"], schema="commerce")

    # --- suppliers ---
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("business_name_hi", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(15), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("gst_number", sa.String(15), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=False),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("village", sa.String(255), nullable=True),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("pincode", sa.String(10), nullable=False),
        sa.Column("seed_license_number", sa.String(50), nullable=True),
        sa.Column("seed_license_url", sa.String(512), nullable=True),
        sa.Column("fertilizer_license_number", sa.String(50), nullable=True),
        sa.Column("fertilizer_license_url", sa.String(512), nullable=True),
        sa.Column("gst_certificate_url", sa.String(512), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_ratings", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'rejected', 'suspended')",
            name="suppliers_status_check",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="suppliers_user_fk"),
        sa.ForeignKeyConstraint(["verified_by"], ["identity.users.id"], ondelete="SET NULL", name="suppliers_verified_by_fk"),
        sa.UniqueConstraint("user_id", name="suppliers_user_unique"),
        schema="commerce",
    )
    op.create_index("idx_suppliers_user", "suppliers", ["user_id"], schema="commerce")
    op.create_index("idx_suppliers_status", "suppliers", ["status"], schema="commerce")
    op.create_index("idx_suppliers_district", "suppliers", ["district", "state"], schema="commerce")

    op.execute("""
        CREATE TRIGGER suppliers_set_updated_at
            BEFORE UPDATE ON commerce.suppliers
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- products ---
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_hi", sa.String(255), nullable=True),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("model_number", sa.String(100), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("mrp", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit", sa.String(20), server_default=sa.text("'piece'"), nullable=False),
        sa.Column("min_order_qty", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("low_stock_threshold", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("is_in_stock", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("additional_images", postgresql.JSONB, nullable=True),
        sa.Column("certifications", postgresql.JSONB, nullable=True),
        sa.Column("active_ingredient", sa.String(255), nullable=True),
        sa.Column("concentration", sa.String(50), nullable=True),
        sa.Column("linked_disease_slug", sa.String(100), nullable=True),
        sa.Column("suitable_crops", postgresql.JSONB, nullable=True),
        sa.Column("rating", sa.Numeric(3, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_reviews", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("price > 0", name="products_price_positive"),
        sa.CheckConstraint("stock_quantity >= 0", name="products_stock_non_negative"),
        sa.ForeignKeyConstraint(["supplier_id"], ["commerce.suppliers.id"], ondelete="CASCADE", name="products_supplier_fk"),
        sa.ForeignKeyConstraint(["category_id"], ["commerce.product_categories.id"], ondelete="RESTRICT", name="products_category_fk"),
        schema="commerce",
    )
    op.create_index("idx_products_supplier", "products", ["supplier_id"], schema="commerce")
    op.create_index("idx_products_category", "products", ["category_id"], schema="commerce")
    op.create_index("idx_products_slug", "products", ["slug"], schema="commerce")
    op.create_index("idx_products_active", "products", ["is_active", "is_in_stock"], postgresql_where=sa.text("is_active = true"), schema="commerce")
    op.create_index("idx_products_disease", "products", ["linked_disease_slug"], postgresql_where=sa.text("linked_disease_slug IS NOT NULL"), schema="commerce")

    op.execute("""
        CREATE TRIGGER products_set_updated_at
            BEFORE UPDATE ON commerce.products
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("order_number", sa.String(50), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("payment_status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_name", sa.String(255), nullable=False),
        sa.Column("shipping_phone", sa.String(15), nullable=False),
        sa.Column("shipping_address_line1", sa.String(255), nullable=False),
        sa.Column("shipping_address_line2", sa.String(255), nullable=True),
        sa.Column("shipping_village", sa.String(255), nullable=True),
        sa.Column("shipping_district", sa.String(100), nullable=False),
        sa.Column("shipping_state", sa.String(100), nullable=False),
        sa.Column("shipping_pincode", sa.String(10), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("payment_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'placed', 'confirmed', 'packed', 'shipped', 'out_for_delivery', 'delivered', 'delivery_failed', 'completed', 'cancelled', 'returned', 'refund_initiated')",
            name="orders_status_check",
        ),
        sa.CheckConstraint(
            "payment_status IN ('pending', 'paid', 'escrow_held', 'released_to_supplier', 'refunded', 'failed')",
            name="orders_payment_status_check",
        ),
        sa.CheckConstraint("total_amount >= 0", name="orders_total_positive"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="orders_farmer_fk"),
        sa.UniqueConstraint("order_number", name="orders_order_number_unique"),
        schema="commerce",
    )
    op.create_index("idx_orders_number", "orders", ["order_number"], schema="commerce")
    op.create_index("idx_orders_farmer", "orders", ["farmer_id"], schema="commerce")
    op.create_index("idx_orders_status", "orders", ["status"], schema="commerce")
    op.create_index("idx_orders_farmer_status", "orders", ["farmer_id", "status"], schema="commerce")

    op.execute("""
        CREATE TRIGGER orders_set_updated_at
            BEFORE UPDATE ON commerce.orders
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- order_items ---
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("product_image_url", sa.String(512), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("fulfillment_status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="order_items_qty_positive"),
        sa.CheckConstraint("unit_price >= 0", name="order_items_price_non_negative"),
        sa.ForeignKeyConstraint(["order_id"], ["commerce.orders.id"], ondelete="CASCADE", name="order_items_order_fk"),
        sa.ForeignKeyConstraint(["product_id"], ["commerce.products.id"], ondelete="RESTRICT", name="order_items_product_fk"),
        sa.ForeignKeyConstraint(["supplier_id"], ["commerce.suppliers.id"], ondelete="RESTRICT", name="order_items_supplier_fk"),
        schema="commerce",
    )
    op.create_index("idx_order_items_order", "order_items", ["order_id"], schema="commerce")
    op.create_index("idx_order_items_product", "order_items", ["product_id"], schema="commerce")
    op.create_index("idx_order_items_supplier", "order_items", ["supplier_id"], schema="commerce")

    # --- shipments ---
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tracking_number", sa.String(100), nullable=True),
        sa.Column("carrier", sa.String(100), nullable=True),
        sa.Column("tracking_url", sa.String(512), nullable=True),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_ids", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["commerce.orders.id"], ondelete="CASCADE", name="shipments_order_fk"),
        sa.ForeignKeyConstraint(["supplier_id"], ["commerce.suppliers.id"], ondelete="RESTRICT", name="shipments_supplier_fk"),
        schema="commerce",
    )
    op.create_index("idx_shipments_order", "shipments", ["order_id"], schema="commerce")
    op.create_index("idx_shipments_tracking", "shipments", ["tracking_number"], schema="commerce")


def downgrade() -> None:
    op.drop_index("idx_shipments_tracking", schema="commerce")
    op.drop_index("idx_shipments_order", schema="commerce")
    op.drop_table("shipments", schema="commerce")

    op.drop_index("idx_order_items_supplier", schema="commerce")
    op.drop_index("idx_order_items_product", schema="commerce")
    op.drop_index("idx_order_items_order", schema="commerce")
    op.drop_table("order_items", schema="commerce")

    op.execute("DROP TRIGGER IF EXISTS orders_set_updated_at ON commerce.orders;")
    op.drop_index("idx_orders_farmer_status", schema="commerce")
    op.drop_index("idx_orders_status", schema="commerce")
    op.drop_index("idx_orders_farmer", schema="commerce")
    op.drop_index("idx_orders_number", schema="commerce")
    op.drop_table("orders", schema="commerce")

    op.execute("DROP TRIGGER IF EXISTS products_set_updated_at ON commerce.products;")
    op.drop_index("idx_products_disease", schema="commerce")
    op.drop_index("idx_products_active", schema="commerce")
    op.drop_index("idx_products_slug", schema="commerce")
    op.drop_index("idx_products_category", schema="commerce")
    op.drop_index("idx_products_supplier", schema="commerce")
    op.drop_table("products", schema="commerce")

    op.execute("DROP TRIGGER IF EXISTS suppliers_set_updated_at ON commerce.suppliers;")
    op.drop_index("idx_suppliers_district", schema="commerce")
    op.drop_index("idx_suppliers_status", schema="commerce")
    op.drop_index("idx_suppliers_user", schema="commerce")
    op.drop_table("suppliers", schema="commerce")

    op.drop_index("idx_prod_cat_type", schema="commerce")
    op.drop_index("idx_prod_cat_slug", schema="commerce")
    op.drop_table("product_categories", schema="commerce")

    op.execute("DROP SCHEMA IF EXISTS commerce CASCADE;")
