# SPIFFE workload identity and short-lived mTLS credentials

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [SPIFFE concepts](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/)

## Problem

Network location and long-lived shared secrets do not provide a durable identity model for workloads that move across clusters, VMs, and environments. A service must authenticate the workload calling it, not merely its IP address.

## Practice

- Assign one SPIFFE ID per workload role inside an explicit trust domain; keep production and non-production trust domains separate.
- Prefer short-lived X.509-SVIDs for mutual TLS. Use JWT-SVIDs only where the transport architecture needs them and evaluate replay exposure.
- Obtain credentials through a Workload API after platform attestation rather than baking private keys into images, repositories, or deployment variables.
- Authorize the verified SPIFFE ID at the receiving service; do not use certificate possession alone as blanket authorization.
- Support trust-bundle and credential rotation without restart, then test it before reducing certificate lifetimes.
- Define federation explicitly when identities cross trust domains; reject unknown trust roots by default.

## Verification

1. Confirm two replica instances with the same approved role can mutually authenticate using rotated credentials.
2. Confirm a workload from staging or another role is rejected by the production authorization policy.
3. Rotate the trust bundle and verify live workloads accept the new material before old material expires.
4. Scan images and deployment manifests for embedded service private keys; none should be required for normal startup.

## Failure modes

- Shared credentials make attribution and revocation impossible at workload granularity.
- A single trust domain collapses the boundary between test and production environments.
- An mTLS handshake is mistaken for authorization, allowing every valid workload to call every service.

## Related

- [SPIFFE overview](https://spiffe.io/docs/latest/spiffe-about/overview/)
