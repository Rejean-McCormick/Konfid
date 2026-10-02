"""production hardening

Revision ID: 9c7e32d4f6a1
Revises: 21d43ef07e30
Create Date: 2026-10-02
"""
from __future__ import annotations

import hashlib
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c7e32d4f6a1"
down_revision: Union[str, None] = "21d43ef07e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _chain_digest(tenant: str, sequence: int, event_digest: str, prev_digest: str) -> str:
    raw = json.dumps(
        {"event": event_digest, "prev": prev_digest, "sequence": sequence, "tenant": tenant},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def upgrade() -> None:
    op.add_column("approval_policies", sa.Column("operator_required", sa.Boolean(), nullable=True))
    op.execute("UPDATE approval_policies SET operator_required = 0 WHERE operator_required IS NULL")
    with op.batch_alter_table("approval_policies") as batch:
        batch.alter_column("operator_required", nullable=False, server_default=sa.false())

    op.add_column("outbox_events", sa.Column("max_attempts", sa.Integer(), nullable=True))
    op.add_column("outbox_events", sa.Column("payload_digest", sa.String(length=128), nullable=True))
    op.add_column("outbox_events", sa.Column("locked_by", sa.String(length=128), nullable=True))
    op.add_column("outbox_events", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("response_actions", sa.Column("operator_principal", sa.String(length=64), nullable=True))
    op.execute("UPDATE outbox_events SET max_attempts = 12 WHERE max_attempts IS NULL")
    with op.batch_alter_table("outbox_events") as batch:
        batch.alter_column("max_attempts", nullable=False, server_default="12")
        batch.create_index("ix_outbox_events_locked_by", ["locked_by"], unique=False)
        batch.create_index("ix_outbox_events_locked_until", ["locked_until"], unique=False)

    op.create_table(
        "audit_heads",
        sa.Column("tenant", sa.String(length=128), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.Column("last_digest", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant"),
    )

    op.add_column("audit_records", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("audit_records", sa.Column("format_version", sa.Integer(), nullable=True))
    op.execute("UPDATE audit_records SET format_version = 1 WHERE format_version IS NULL")
    op.add_column("audit_records", sa.Column("prev_digest", sa.String(length=128), nullable=True))
    op.add_column("audit_records", sa.Column("chain_digest", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, tenant, event_digest FROM audit_records ORDER BY tenant, created_at, id")
    ).mappings().all()
    heads: dict[str, tuple[int, str]] = {}
    for row in rows:
        seq, prev = heads.get(row["tenant"], (0, "GENESIS"))
        seq += 1
        chain = _chain_digest(row["tenant"], seq, row["event_digest"], prev)
        bind.execute(
            sa.text(
                "UPDATE audit_records SET sequence=:sequence, prev_digest=:prev, chain_digest=:chain WHERE id=:id"
            ),
            {"sequence": seq, "prev": prev, "chain": chain, "id": row["id"]},
        )
        heads[row["tenant"]] = (seq, chain)

    for tenant, (seq, chain) in heads.items():
        bind.execute(
            sa.text(
                "INSERT INTO audit_heads (tenant,last_sequence,last_digest,updated_at) "
                "VALUES (:tenant,:sequence,:digest,CURRENT_TIMESTAMP)"
            ),
            {"tenant": tenant, "sequence": seq, "digest": chain},
        )

    with op.batch_alter_table("audit_records") as batch:
        batch.alter_column("sequence", nullable=False)
        batch.alter_column("format_version", nullable=False, server_default="3")
        batch.alter_column("prev_digest", nullable=False)
        batch.alter_column("chain_digest", nullable=False)
        batch.create_unique_constraint("uq_audit_tenant_sequence", ["tenant", "sequence"])
        batch.create_index("ix_audit_records_chain_digest", ["chain_digest"], unique=False)

    op.add_column("audit_records", sa.Column("export_attempts", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("audit_records", sa.Column("export_next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("audit_records", sa.Column("export_last_error", sa.Text(), nullable=True))
    op.add_column("audit_records", sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE audit_records SET export_next_attempt_at = created_at WHERE export_next_attempt_at IS NULL")
    with op.batch_alter_table("audit_records") as batch:
        batch.alter_column("export_attempts", nullable=False, server_default="0")
    op.create_index("ix_audit_records_export_next_attempt_at", "audit_records", ["export_next_attempt_at"], unique=False)

    op.create_table(
        "rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=128), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index("ix_rate_limit_buckets_window_started_at", "rate_limit_buckets", ["window_started_at"], unique=False)
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rate_limit_buckets_expires_at", table_name="rate_limit_buckets")
    op.drop_index("ix_rate_limit_buckets_window_started_at", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")

    op.drop_index("ix_audit_records_export_next_attempt_at", table_name="audit_records")
    with op.batch_alter_table("audit_records") as batch:
        batch.drop_index("ix_audit_records_chain_digest")
        batch.drop_column("exported_at")
        batch.drop_column("export_last_error")
        batch.drop_column("export_next_attempt_at")
        batch.drop_column("export_attempts")
        batch.drop_constraint("uq_audit_tenant_sequence", type_="unique")
        batch.drop_column("chain_digest")
        batch.drop_column("prev_digest")
        batch.drop_column("format_version")
        batch.drop_column("sequence")
    op.drop_table("audit_heads")

    with op.batch_alter_table("outbox_events") as batch:
        batch.drop_index("ix_outbox_events_locked_until")
        batch.drop_index("ix_outbox_events_locked_by")
        batch.drop_column("dead_lettered_at")
        batch.drop_column("locked_until")
        batch.drop_column("locked_by")
        batch.drop_column("payload_digest")
        batch.drop_column("max_attempts")
    op.drop_column("response_actions", "operator_principal")

    with op.batch_alter_table("approval_policies") as batch:
        batch.drop_column("operator_required")
