import threading

import pytest
from sqlalchemy import select

from konfid.adapters.audit import AuditSink
from konfid.db import SessionLocal, engine
from konfid.models import AuditRecord, OutboxEvent
from konfid.services.audit_verify import verify_chain
from konfid.services.outbox import _claim
from konfid.utils import digest, new_id


postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="requires PostgreSQL row/advisory locking"
)


@postgres_only
def test_postgres_concurrent_audit_writers_preserve_single_chain():
    writers = 12
    barrier = threading.Barrier(writers)
    errors: list[BaseException] = []

    def write_one(index: int):
        try:
            with SessionLocal() as db:
                barrier.wait(timeout=10)
                AuditSink().record(
                    db,
                    tenant="pg-concurrent-audit",
                    actor=f"P{index}",
                    caller="svc:pg-test",
                    action="concurrency.test",
                    target=f"resource:{index}",
                    outcome="SUCCESS",
                    correlation_id=f"corr-{index}",
                    details={"writer": index},
                )
                db.commit()
        except BaseException as exc:  # surfaced in the main test thread below
            errors.append(exc)

    threads = [threading.Thread(target=write_one, args=(i,), daemon=True) for i in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    with SessionLocal() as db:
        rows = db.scalars(
            select(AuditRecord)
            .where(AuditRecord.tenant == "pg-concurrent-audit")
            .order_by(AuditRecord.sequence)
        ).all()
        assert [row.sequence for row in rows] == list(range(1, writers + 1))
        assert verify_chain(db, "pg-concurrent-audit")["valid"] is True


@postgres_only
def test_postgres_outbox_workers_claim_distinct_rows():
    ids = [new_id("OUT"), new_id("OUT")]
    with SessionLocal() as db:
        for index, event_id in enumerate(ids):
            payload = {"n": index}
            db.add(
                OutboxEvent(
                    id=event_id,
                    tenant="pg-outbox",
                    topic="test.claim.v1",
                    aggregate_ref=f"aggregate-{index}",
                    payload=payload,
                    payload_digest=digest(payload),
                    max_attempts=3,
                )
            )
        db.commit()

    barrier = threading.Barrier(2)
    claimed: list[tuple[str, str]] = []
    errors: list[BaseException] = []

    def claim_one(worker: str):
        try:
            with SessionLocal() as db:
                barrier.wait(timeout=10)
                rows = _claim(db, worker, 1)
                if rows:
                    claimed.append((worker, rows[0].id))
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=claim_one, args=("pg-worker-a",), daemon=True),
        threading.Thread(target=claim_one, args=("pg-worker-b",), daemon=True),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(claimed) == 2
    assert len({event_id for _, event_id in claimed}) == 2
