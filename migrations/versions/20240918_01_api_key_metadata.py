"""Add API key metadata columns"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240918_01"
down_revision = "d12d62621b66"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("api_keys", sa.Column("token_prefix", sa.String(length=16)))
    op.add_column("api_keys", sa.Column("token_last4", sa.String(length=4)))
    op.add_column("api_keys", sa.Column("revoked_at", sa.DateTime()))


def downgrade():
    op.drop_column("api_keys", "revoked_at")
    op.drop_column("api_keys", "token_last4")
    op.drop_column("api_keys", "token_prefix")
