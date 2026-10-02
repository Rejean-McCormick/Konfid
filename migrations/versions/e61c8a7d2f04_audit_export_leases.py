"""audit export leases

Revision ID: e61c8a7d2f04
Revises: 9c7e32d4f6a1
Create Date: 2026-10-02
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e61c8a7d2f04"
down_revision: Union[str, None] = "9c7e32d4f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_records", sa.Column("export_locked_by", sa.String(length=128), nullable=True))
    op.add_column("audit_records", sa.Column("export_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_audit_records_export_locked_by", "audit_records", ["export_locked_by"], unique=False)
    op.create_index("ix_audit_records_export_locked_until", "audit_records", ["export_locked_until"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_records_export_locked_until", table_name="audit_records")
    op.drop_index("ix_audit_records_export_locked_by", table_name="audit_records")
    op.drop_column("audit_records", "export_locked_until")
    op.drop_column("audit_records", "export_locked_by")
