"""Add trial extension days to coupons"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240919_01"
down_revision = "20240918_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "coupons",
        sa.Column("trial_extension_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("coupons", "trial_extension_days", server_default=None)


def downgrade():
    op.drop_column("coupons", "trial_extension_days")
