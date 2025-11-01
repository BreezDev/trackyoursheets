"""Switch to Resend emails and add notification preferences/2FA."""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20240921_01_resend_notifications_and_2fa"
down_revision = "20240920_01_enable_starter_producer_portal"
branch_labels = None
depends_on = None


DEFAULT_NOTIFICATION_PREFERENCES = {
    "signup": True,
    "login": True,
    "workspace_invite": True,
    "plan_updates": True,
    "workspace_updates": True,
    "new_entries": True,
    "general_updates": True,
}


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("notification_preferences", sa.JSON(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "two_factor_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_secret", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("two_factor_expires_at", sa.DateTime(), nullable=True),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE users SET notification_preferences = :prefs WHERE notification_preferences IS NULL"
        ),
        {"prefs": json.dumps(DEFAULT_NOTIFICATION_PREFERENCES)},
    )
    connection.execute(
        sa.text(
            "UPDATE users SET two_factor_enabled = true WHERE two_factor_enabled IS NULL"
        )
    )

    op.alter_column(
        "users",
        "two_factor_enabled",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("users", "two_factor_expires_at")
    op.drop_column("users", "two_factor_secret")
    op.drop_column("users", "two_factor_enabled")
    op.drop_column("users", "notification_preferences")
