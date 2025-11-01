"""Add workspace memberships, password flags, and pricing fields."""
from alembic import op
"""Add workspace memberships, password flags, and pricing fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


revision = "20240922_01_memberships_and_pricing_updates"
down_revision = "20240921_01_resend_notifications_and_2fa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscription_plans",
        sa.Column("included_users", sa.Integer(), nullable=True),
    )
    op.add_column(
        "subscription_plans",
        sa.Column("extra_user_price", sa.Numeric(10, 2), nullable=True),
    )

    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "office_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("office_id", sa.Integer(), sa.ForeignKey("offices.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "office_id", name="uq_office_memberships_user_office"),
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "workspace_id", name="uq_workspace_memberships_user_workspace"),
    )

    op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    op.drop_table("workspace_memberships")
    op.drop_table("office_memberships")
    op.drop_column("users", "must_change_password")
    op.drop_column("subscription_plans", "extra_user_price")
    op.drop_column("subscription_plans", "included_users")
