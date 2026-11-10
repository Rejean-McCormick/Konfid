# Branch 08 — Konfid to kOA Governance Policy Runtime boundary

**Status:** `SPEC_DECISION_REQUIRED` for the production transport adapter. This document records observed interfaces, not an adopted bridge.

## Observed Konfid producer/consumer expectation

`src/konfid/adapters/policy.py::KoaPolicyEngine` currently calls HTTP `POST /v1/evaluate` with one of these shapes:

- `{"kind":"access","context": <Konfid AccessRequest>}` and expects `AccessResponse` fields `decision_id`, `decision`, `policy`, `reason_codes`, `obligations`, and for `ALLOW` a timezone-aware `valid_until` strictly within 60 seconds.
- `kind=control` with tenant/actor/action/target/scope and assurance context;
- `kind=response` with requester/operation/target/scope, assurance and approval context.

Invalid/malformed positive responses, missing short TTL, unavailable policy or unsupported decision values are blocked. Production settings require the `koa` engine; no fallback to development policy is permitted.

## Different kOA-side interface

The supplied kOA-Linux `components/governance-policy-runtime` implements typed `evaluate_decision` (`IFACE-GOV-POL-001`) with `PolicyEvaluationRequest` / `PolicyEvaluationResponse` / `DecisionReceipt`; it requires registered decision classes, closed `evaluation_context`, a policy set reference, authority version and correlated IDs. Those are **not** the same JSON wire shapes and the kOA native response is not directly a Konfid `AccessResponse`. The branch tests affirm that the two raw envelopes reject one another rather than being implicitly interpreted as an `ALLOW`.

## Required owner decision before connection

1. Name the real transport endpoint/adapter owner (HTTP sidecar, trusted local service adapter or another explicitly selected transport), exact schema/profile ID and compatible revisions. Do not infer `/v1/evaluate` exists as a kOA-Linux HTTP route.
2. Map authenticated identities/tenants, registered actions, resources and scopes into the correct kOA decision class and closed context with no scope widening.
3. Enforce the mapping of kOA `result`, policy set, authority/receipt correlation and required obligations into Konfid's bounded `ALLOW/DENY/BLOCKED` plus explicit fresh `valid_until`. The native kOA response **does not itself establish Konfid's 60-second TTL**; choose an authoritative expiry rule and test it.
4. Require deny-on-unavailable, stale authority, unknown obligation, bad tenant/correlation, altered digest and an unfulfilled audit requirement. The final effect remains enforced by the owner product PEP, not by a policy HTTP 200.
5. Run the complete two-endpoint contract matrix and live/trusted-policy service availability tests before production or cross-repo publication.

## Local proof

`python -m pytest -q tests/test_branch08_koa_policy_bridge.py tests/test_tandem_koa_allow_ttl.py`

This proves fail-closed handling of the supplied incompatible envelope and response TTL rules; no actual inter-system network policy decisions have been exercised.
