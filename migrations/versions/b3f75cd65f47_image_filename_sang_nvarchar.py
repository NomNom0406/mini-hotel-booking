"""image_filename sang NVARCHAR

Revision ID: b3f75cd65f47
Revises: 03aa61042e80
Create Date: 2026-11-04 19:12:53.962234

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f75cd65f47'
down_revision = '03aa61042e80'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "hotels", "image_filename",
        existing_type=sa.String(length=255),
        type_=sa.Unicode(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "room_types", "image_filename",
        existing_type=sa.String(length=255),
        type_=sa.Unicode(length=255),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "room_types", "image_filename",
        existing_type=sa.Unicode(length=255),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "hotels", "image_filename",
        existing_type=sa.Unicode(length=255),
        type_=sa.String(length=255),
        existing_nullable=True,
    )