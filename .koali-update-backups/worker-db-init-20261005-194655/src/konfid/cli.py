from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import time
import uuid

from .auth import make_dev_token
from .adapters.http import close_http_clients
from .config import get_settings
from .db import SessionLocal, database_ready, init_db
from .services.audit_export import export_pending
from .services.audit_verify import verify_chain
from .services.bootstrap import bootstrap_tenant
from .services.outbox import process_pending

_STOP = False


def _stop(*_):
    global _STOP
    _STOP = True


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _cycle(worker_id: str):
    with SessionLocal() as db:
        published = process_pending(db, worker_id=worker_id)
    with SessionLocal() as db:
        exported = export_pending(db, worker_id=worker_id)
    return published, exported


def main():
    p = argparse.ArgumentParser(prog="konfid")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    t = sub.add_parser("dev-token")
    t.add_argument("--subject", required=True)
    t.add_argument("--tenant", required=True)
    t.add_argument("--scopes", default="konfid:*")
    t.add_argument("--actor", action="store_true")
    t.add_argument("--assurance", default="phishing_resistant")
    t.add_argument("--authorized-party")
    b = sub.add_parser("bootstrap-tenant")
    b.add_argument("tenant")
    sub.add_parser("process-outbox")
    sub.add_parser("export-audit")
    v = sub.add_parser("verify-audit")
    v.add_argument("tenant")
    sub.add_parser("doctor")
    w = sub.add_parser("worker")
    w.add_argument("--interval", type=float, default=None)
    w.add_argument("--once", action="store_true")
    args = p.parse_args()
    settings = get_settings()

    if args.cmd == "init-db":
        if not settings.dev_mode:
            raise SystemExit("init-db is development-only; use `alembic upgrade head` in production")
        init_db()
        print("database initialized")
    elif args.cmd == "dev-token":
        if not settings.dev_mode:
            raise SystemExit("dev-token is disabled in production")
        extra = None
        if args.actor:
            now = int(time.time())
            extra = {"assurance": args.assurance, "auth_time": now}
            if args.authorized_party:
                extra["azp"] = args.authorized_party
        print(make_dev_token(args.subject, args.tenant, args.scopes.split(","), actor=args.actor, extra=extra))
    elif args.cmd == "bootstrap-tenant":
        if settings.dev_mode:
            init_db()
        with SessionLocal() as db:
            policies = bootstrap_tenant(db, args.tenant)
            db.commit()
            print(json.dumps({"tenant": args.tenant, "policies": [x.operation for x in policies]}))
    elif args.cmd == "process-outbox":
        with SessionLocal() as db:
            print(json.dumps({"published": process_pending(db, worker_id=_worker_id())}))
    elif args.cmd == "export-audit":
        with SessionLocal() as db:
            print(json.dumps({"exported": export_pending(db, worker_id=_worker_id())}))
    elif args.cmd == "verify-audit":
        with SessionLocal() as db:
            result = verify_chain(db, args.tenant)
            print(json.dumps(result))
            if not result["valid"]:
                raise SystemExit(2)
    elif args.cmd == "doctor":
        ok, reason = database_ready()
        print(json.dumps({"configuration": "valid", "database_ready": ok, "database_reason": reason, "version": settings.version}))
        if not ok:
            raise SystemExit(2)
    elif args.cmd == "worker":
        interval = args.interval if args.interval is not None else settings.worker_interval_seconds
        worker_id = _worker_id()
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        try:
            while not _STOP:
                published, exported = _cycle(worker_id)
                if args.once:
                    print(json.dumps({"worker_id": worker_id, "published": published, "exported": exported}))
                    break
                time.sleep(max(0.1, interval))
        finally:
            close_http_clients()
