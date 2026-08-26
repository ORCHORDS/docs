# DNS HTTPS/SVCB Downgrade and Internal-Target Controls

**Issue:** HTTPS and SVCB records can steer clients to protocols, ports, and addresses. Inconsistent records can cause downgrade, denial, or unintended access to internal services.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Process AliasMode and ServiceMode according to RFC 9460 and fail when mandatory parameters are unsupported.
- Treat disappearance or inconsistency after receiving a usable record as a possible downgrade, according to client policy.
- Apply address-scope and port restrictions before connecting to targets supplied by untrusted DNS contexts.
- Use authenticated DNS where the threat model requires origin assurance; HTTPS does not authenticate the DNS answer itself.

## Verification

- Remove SvcParams between retries and verify downgrade detection.
- Return mandatory unknown keys and confirm the record is unusable.
- Return loopback, link-local, or private targets and confirm policy blocks unintended access.

## Gotchas

- AliasMode dot can be forged for targeted denial of service.
- Fallback rules must not silently discard security parameters.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9460.html
