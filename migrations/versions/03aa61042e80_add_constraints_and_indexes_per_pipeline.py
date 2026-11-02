"""add constraints and indexes per pipeline

Revision ID: 03aa61042e80
Revises: dd9def071965
Create Date: 2026-11-01 17:28:34.683444

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '03aa61042e80'
down_revision = 'dd9def071965'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('hotels', schema=None) as batch_op:
        batch_op.create_index('ix_hotels_province', ['province'], unique=False)
        batch_op.create_unique_constraint('uq_hotels_name', ['name'])
        batch_op.create_check_constraint('star_rating_range', 'star_rating BETWEEN 1 AND 5')

    with op.batch_alter_table('room_types', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_room_types_hotel_name', ['hotel_id', 'name'])
        batch_op.create_check_constraint('base_price_positive', 'base_price > 0')
        batch_op.create_check_constraint('capacity_min', 'capacity >= 1')

    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index('ix_bookings_room_dates', ['room_id', 'check_in', 'check_out'], unique=False)
        batch_op.create_index('ix_bookings_status', ['status'], unique=False)
        batch_op.create_check_constraint('checkout_after_checkin', 'check_out > check_in')
        batch_op.create_check_constraint('guests_positive', 'guests > 0')


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_constraint('guests_positive', type_='check')
        batch_op.drop_constraint('checkout_after_checkin', type_='check')
        batch_op.drop_index('ix_bookings_status')
        batch_op.drop_index('ix_bookings_room_dates')

    with op.batch_alter_table('room_types', schema=None) as batch_op:
        batch_op.drop_constraint('capacity_min', type_='check')
        batch_op.drop_constraint('base_price_positive', type_='check')
        batch_op.drop_constraint('uq_room_types_hotel_name', type_='unique')

    with op.batch_alter_table('hotels', schema=None) as batch_op:
        batch_op.drop_constraint('star_rating_range', type_='check')
        batch_op.drop_constraint('uq_hotels_name', type_='unique')
        batch_op.drop_index('ix_hotels_province')