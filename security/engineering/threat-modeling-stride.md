# threat-modeling-stride

**Issue:** Ad-hoc security reviews miss systematic threat categories that structured threat modeling catches
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Security reviews that start from known vulnerability lists (OWASP Top 10) miss system-specific threats. STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) provides a systematic framework applicable to any architecture.

## Pattern / Solution
```
STRIDE per element — apply to each DFD component:

| Category              | Question                                        | Control                          |
|-----------------------|-------------------------------------------------|----------------------------------|
| Spoofing              | Can an actor pretend to be another?             | Authentication, MFA              |
| Tampering             | Can data be modified in transit or at rest?     | Integrity checks, signing        |
| Repudiation           | Can actions be denied after the fact?           | Audit logs, non-repudiation      |
| Information Disclosure| Can secrets be exposed?                         | Encryption, need-to-know         |
| Denial of Service     | Can availability be disrupted?                  | Rate limiting, redundancy        |
| Elevation of Privilege| Can an actor gain unauthorized capabilities?    | Authorization, least privilege   |
```
```markdown
# Threat model template (per data flow)
## Data flow: User → API → Database
- S: Is the user identity verified? (JWT + MFA)
- T: Is the request body validated and signed? (HMAC)
- R: Are all writes logged with user ID? (audit log)
- I: Is PII encrypted in transit and at rest? (TLS + AES-256)
- D: Are there rate limits on the API? (100 req/min)
- E: Does the API enforce RBAC? (role check on every endpoint)
```

## Gotchas
- Threat modeling should happen at design time, not after code is written.
- STRIDE per element is more thorough than STRIDE per interaction — apply to every process, data store, and external entity.
- Prioritize threats by likelihood × impact (DREAD or CVSS-like scoring).
- Revisit the threat model on every major architecture change.

## Related
- `attack-surface-reduction.md`
- `sast-false-positive-management.md`
