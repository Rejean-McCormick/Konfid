# Authentication and authorization

## Human authentication

Konfid does not collect passwords. Konnaxion, Orgo and a Konfid UI can use the same federation authority while keeping independent application sessions. Google can be the default user experience; canonical federation remains OIDC `issuer + sub`, never email.

## Workload authentication

Every protected API call authenticates the **calling service** independently from the human actor. Production validates an asymmetric, short-lived workload JWT against `KONFID_WORKLOAD_JWKS_URL`, expected issuer/audience and bounded lifetime. Production requires `jti` and rejects the development wildcard scope.

## Human actor assertion

Sensitive operations carry `X-Konfid-Actor-Token`, verified independently against `KONFID_ACTOR_JWKS_URL`. Production requires:

- `sub` matching the requested Principal;
- tenant match;
- `jti`;
- authentication assurance;
- `auth_time`;
- bounded lifetime;
- `azp` or `client_id` matching the authenticated workload service.

This prevents a compromised/buggy application from upgrading assurance by merely sending `auth_assurance=phishing_resistant` in JSON.

## Sessions

Konnaxion, Orgo and Konfid keep separate local sessions. They do not pass cookies to each other. Shared SSO is achieved through the common IdP/federation session.

## Authorization

The effective model combines RBAC, resource class, scope, context, delegation and obligations. In production, kOA Governance Policy Runtime is authoritative. An application may be stricter than Konfid but must not convert a Konfid deny on a governed path into allow.

## Step-up

Policies can require stronger/recent authentication for sensitive actions. The application sends the user through the IdP step-up flow, obtains a fresh actor assertion, then retries authorization.

## Service-to-service rule

Always preserve both identities:

```text
caller_service = svc:konnaxion-prod
actor_principal = P123
```

A Google user token is not a generic service credential.
