"""Stub revision to restore missing 'update_fsm_v4' in Alembic graph.

This project contains a merge revision (8d343d3359eb) that references
'update_fsm_v4' as one of its down revisions, but the corresponding
revision file is missing. This stub restores the revision node so Alembic
can build the revision map again.

No-op by design.
"""

from alembic import op

# IMPORTANT: revision id must match the missing one exactly
revision = "update_fsm_v4"

# Anchor to the known revision referenced by the merge
down_revision = "12552b9e63f5"

branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
