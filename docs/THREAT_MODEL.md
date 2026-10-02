# Threat model summary

Protected assets include identity bindings, grants, policy state, response authority, approval receipts, signing credentials and audit evidence.

Key threats and structural mitigations:

- **Compromised email:** email cannot establish canonical identity.
- **Compromised Konnaxion:** workload scopes and actor assertions prevent arbitrary cross-system authority.
- **Compromised Orgo:** Orgo cannot execute; Konfid revalidates approver roles, digest and quorum.
- **Compromised detector:** detectors have no enforcement credentials.
- **False positive:** response policy and minimal containment sit between signal and action.
- **Replay/duplicate:** action IDs, idempotency keys and receipts.
- **Cross-tenant confusion:** authenticated caller tenant is checked against request tenant.
- **Telemetry DoS:** production should isolate Overwatch workers from authorization/revocation capacity.
- **IdP outage:** existing bounded sessions and sovereign break-glass paths remain separate concerns.
- **Insider admin:** avoid wildcard credentials; use separation of duties, short-lived elevation and immutable audit.
