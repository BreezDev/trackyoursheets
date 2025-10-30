"""Enable producer portals on Starter plan"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20240920_01"
down_revision = "20240919_01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE subscription_plans
        SET includes_producer_portal = TRUE
        WHERE lower(name) = 'starter'
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE subscription_plans
        SET includes_producer_portal = FALSE
        WHERE lower(name) = 'starter'
        """
    )
