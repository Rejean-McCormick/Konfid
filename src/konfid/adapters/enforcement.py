from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import re

from ..config import get_settings
from ..utils import as_utc_naive, digest, utcnow
from .http import JsonHttpAdapter

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class EnforcementAdapter(ABC):
    @abstractmethod
    def execute(self, command: dict) -> dict:
        ...


def _bounded_text(value, field: str, limit: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise RuntimeError(f"RECEIPT_{field.upper()}_MISSING")
        return None
    if not isinstance(value, str) or not value or len(value) > limit:
        raise RuntimeError(f"RECEIPT_{field.upper()}_INVALID")
    return value


def _receipt_time(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise RuntimeError("RECEIPT_EXECUTED_AT_INVALID")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("RECEIPT_EXECUTED_AT_INVALID") from exc
    return as_utc_naive(dt).isoformat(timespec="microseconds") + "Z"


def validate_receipt(command: dict, receipt: dict) -> dict:
    """Validate and minimize an enforcement receipt before persistence/audit.

    Unknown upstream fields are intentionally discarded. This avoids turning a
    privileged transport response into an unbounded or secret-bearing audit
    payload while retaining the fields needed for reconciliation.
    """
    if not isinstance(receipt, dict):
        raise RuntimeError("INVALID_ENFORCEMENT_RECEIPT")
    if receipt.get("action_id") != command["action_id"]:
        raise RuntimeError("RECEIPT_ACTION_MISMATCH")
    status = receipt.get("status")
    if status not in {"EXECUTED", "REJECTED", "FAILED", "UNKNOWN"}:
        raise RuntimeError("RECEIPT_STATUS_INVALID")

    executor = _bounded_text(receipt.get("executor"), "executor", 256, required=True)
    receipt_version = _bounded_text(receipt.get("receipt_version"), "version", 32, required=True)
    software_version = _bounded_text(receipt.get("software_version"), "software_version", 128)
    reason_code = _bounded_text(receipt.get("reason_code"), "reason_code", 128)
    state_digest = receipt.get("target_state_digest")
    if state_digest is not None and (not isinstance(state_digest, str) or not _DIGEST_RE.fullmatch(state_digest)):
        raise RuntimeError("RECEIPT_STATE_DIGEST_INVALID")
    if status == "EXECUTED" and not state_digest:
        raise RuntimeError("RECEIPT_STATE_DIGEST_MISSING")

    normalized = {
        "action_id": command["action_id"],
        "executor": executor,
        "status": status,
        "executed_at": _receipt_time(receipt.get("executed_at")),
        "target_state_digest": state_digest,
        "software_version": software_version,
        "receipt_version": receipt_version,
        "reason_code": reason_code,
    }
    normalized["receipt_digest"] = digest(normalized)
    return normalized


class LocalEnforcementAdapter(EnforcementAdapter):
    def __init__(self):
        self.receipts: dict[str, dict] = {}

    def execute(self, command: dict):
        if command["action_id"] in self.receipts:
            return self.receipts[command["action_id"]]
        r = {
            "action_id": command["action_id"],
            "executor": "svc:konfid-local-enforcement",
            "status": "EXECUTED",
            "executed_at": utcnow().isoformat() + "Z",
            "target_state_digest": digest(
                {"target": command["target"], "operation": command["operation"]}
            ),
            "software_version": "konfid-local/2",
            "receipt_version": "1",
        }
        normalized = validate_receipt(command, r)
        self.receipts[command["action_id"]] = normalized
        return normalized


class InteractionKernelEnforcementAdapter(EnforcementAdapter):
    def __init__(self, url):
        self.http = JsonHttpAdapter(url, get_settings().integration_secret("interaction_kernel"))

    def execute(self, command):
        receipt = self.http.post(
            "/v1/messages/konfid.response.execute",
            command,
            headers={"Idempotency-Key": command["idempotency_key"]},
            idempotent=True,
        )
        return validate_receipt(command, receipt)


_LOCAL = LocalEnforcementAdapter()


def get_enforcement_adapter():
    s = get_settings()
    if s.interaction_kernel_url:
        return InteractionKernelEnforcementAdapter(s.interaction_kernel_url)
    if not s.dev_mode:
        raise RuntimeError("PRODUCTION_ENFORCEMENT_ADAPTER_NOT_CONFIGURED")
    return _LOCAL
