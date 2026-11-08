"""add is_charged to bookings

Revision ID: 7439520ee368
Revises: b3f75cd65f47
Create Date: 2026-11-08 18:57:39.694964

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7439520ee368'
down_revision = 'b3f75cd65f47'
branch_labels = None
depends_on = None


def upgrade():
    # thêm cột nullable, điền False cho dòng cũ, rồi đặt NOT NULL
    # (không dùng server_default để downgrade không vướng default constraint của SQL Server)
    op.add_column("bookings", sa.Column("is_charged", sa.Boolean(), nullable=True))
    bookings = sa.table("bookings", sa.column("is_charged", sa.Boolean()))
    op.execute(bookings.update().values(is_charged=False))
    op.alter_column("bookings", "is_charged",
                    existing_type=sa.Boolean(), nullable=False, existing_nullable=True)


def downgrade():
    op.drop_column("bookings", "is_charged")