"""Seed product categories for the marketplace

Populates commerce.product_categories with the main agricultural input
categories used in India.

NO MOCK DATA — these are real product categories used by Indian agri-input
suppliers (seeds, fertilizers, pesticides, machinery, etc.).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-19

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CATEGORIES = [
    # Top-level categories
    {"slug": "seeds", "name": "Seeds", "name_hi": "बीज", "category_type": "seeds", "icon": "Sprout", "sort_order": 1},
    {"slug": "fertilizers", "name": "Fertilizers", "name_hi": "उर्वरक", "category_type": "fertilizers", "icon": "FlaskConical", "sort_order": 2},
    {"slug": "pesticides", "name": "Pesticides", "name_hi": "कीटनाशक", "category_type": "pesticides", "icon": "Shield", "sort_order": 3},
    {"slug": "fungicides", "name": "Fungicides", "name_hi": "फफूंदनाशक", "category_type": "fungicides", "icon": "Shield", "sort_order": 4},
    {"slug": "herbicides", "name": "Herbicides", "name_hi": "खरपतवार नाशी", "category_type": "herbicides", "icon": "Shield", "sort_order": 5},
    {"slug": "machinery", "name": "Farm Machinery", "name_hi": "कृषि मशीनरी", "category_type": "machinery", "icon": "Tractor", "sort_order": 6},
    {"slug": "tools", "name": "Farm Tools", "name_hi": "कृषि उपकरण", "category_type": "tools", "icon": "Wrench", "sort_order": 7},
    {"slug": "irrigation", "name": "Irrigation", "name_hi": "सिंचाई", "category_type": "irrigation", "icon": "Droplets", "sort_order": 8},
    {"slug": "organic_inputs", "name": "Organic Inputs", "name_hi": "जैविक उपकरण", "category_type": "organic_inputs", "icon": "Leaf", "sort_order": 9},
    {"slug": "other", "name": "Other", "name_hi": "अन्य", "category_type": "other", "icon": "Package", "sort_order": 99},

    # Sub-categories (seeds)
    {"slug": "cereal_seeds", "name": "Cereal Seeds", "name_hi": "अनाज बीज", "category_type": "seeds", "parent_slug": "seeds", "sort_order": 1},
    {"slug": "pulse_seeds", "name": "Pulse Seeds", "name_hi": "दलहन बीज", "category_type": "seeds", "parent_slug": "seeds", "sort_order": 2},
    {"slug": "oilseed_seeds", "name": "Oilseed Seeds", "name_hi": "तिलहन बीज", "category_type": "seeds", "parent_slug": "seeds", "sort_order": 3},
    {"slug": "vegetable_seeds", "name": "Vegetable Seeds", "name_hi": "सब्जी बीज", "category_type": "seeds", "parent_slug": "seeds", "sort_order": 4},
    {"slug": "fruit_seeds", "name": "Fruit Seeds", "name_hi": "फल बीज", "category_type": "seeds", "parent_slug": "seeds", "sort_order": 5},

    # Sub-categories (fertilizers)
    {"slug": "npk_fertilizers", "name": "NPK Fertilizers", "name_hi": "NPK उर्वरक", "category_type": "fertilizers", "parent_slug": "fertilizers", "sort_order": 1},
    {"slug": "urea", "name": "Urea", "name_hi": "यूरिया", "category_type": "fertilizers", "parent_slug": "fertilizers", "sort_order": 2},
    {"slug": "micronutrients", "name": "Micronutrients", "name_hi": "सूक्ष्म पोषक", "category_type": "fertilizers", "parent_slug": "fertilizers", "sort_order": 3},
    {"slug": "bio_fertilizers", "name": "Bio Fertilizers", "name_hi": "जैव उर्वरक", "category_type": "fertilizers", "parent_slug": "fertilizers", "sort_order": 4},

    # Sub-categories (machinery)
    {"slug": "tractors", "name": "Tractors", "name_hi": "ट्रैक्टर", "category_type": "machinery", "parent_slug": "machinery", "sort_order": 1},
    {"slug": "harvesters", "name": "Harvesters", "name_hi": "हार्वेस्टर", "category_type": "machinery", "parent_slug": "machinery", "sort_order": 2},
    {"slug": "tillers", "name": "Tillers / Rotavators", "name_hi": "टिलर", "category_type": "machinery", "parent_slug": "machinery", "sort_order": 3},
    {"slug": "pumps", "name": "Water Pumps", "name_hi": "पानी पंप", "category_type": "machinery", "parent_slug": "machinery", "sort_order": 4},
    {"slug": "sprayers", "name": "Sprayers", "name_hi": "स्प्रेयर", "category_type": "machinery", "parent_slug": "machinery", "sort_order": 5},
]


def upgrade() -> None:
    categories_table = sa.table(
        "product_categories",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("name_hi", sa.String),
        sa.column("parent_id", postgresql_uuid()),
        sa.column("category_type", sa.String),
        sa.column("icon", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        schema="commerce",
    )

    # First insert top-level categories (no parent)
    top_level = [c for c in CATEGORIES if "parent_slug" not in c]
    op.bulk_insert(categories_table, [
        {
            "slug": c["slug"],
            "name": c["name"],
            "name_hi": c.get("name_hi"),
            "parent_id": None,
            "category_type": c["category_type"],
            "icon": c.get("icon"),
            "is_active": True,
            "sort_order": c.get("sort_order", 0),
        }
        for c in top_level
    ])

    # Then insert sub-categories with parent_id resolved via slug lookup
    from sqlalchemy import text
    conn = op.get_bind()
    for cat in CATEGORIES:
        if "parent_slug" not in cat:
            continue
        parent_slug = cat["parent_slug"]
        result = conn.execute(
            text("SELECT id FROM commerce.product_categories WHERE slug = :slug"),
            {"slug": parent_slug},
        )
        parent_id = result.scalar_one_or_none()
        if parent_id:
            conn.execute(
                text("""
                    INSERT INTO commerce.product_categories
                        (slug, name, name_hi, parent_id, category_type, is_active, sort_order)
                    VALUES
                        (:slug, :name, :name_hi, :parent_id, :category_type, true, :sort_order)
                """),
                {
                    "slug": cat["slug"],
                    "name": cat["name"],
                    "name_hi": cat.get("name_hi"),
                    "parent_id": parent_id,
                    "category_type": cat["category_type"],
                    "sort_order": cat.get("sort_order", 0),
                },
            )


def postgresql_uuid():
    from sqlalchemy.dialects.postgresql import UUID
    return UUID(as_uuid=True)


def downgrade() -> None:
    # slugs is built from the static CATEGORIES list above, not user input
    slugs = ", ".join(f"'{c['slug']}'" for c in CATEGORIES)
    op.execute(f"DELETE FROM commerce.product_categories WHERE slug IN ({slugs})")  # noqa: S608
