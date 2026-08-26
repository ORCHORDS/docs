# secrets-management-comparison

**Issue:** Secrets management — Vault vs cloud-native
**Date:** 2026-08-09
**Status:** documented

## Symptom
Secrets in .env files. Git-committed credentials. A
leak in CI logs. The on-call is paged. You wish you
had a real secrets manager.

## Root cause
**Secrets in files are not safe.** Use a manager.

**Source:** CloudToolStack 2026 comparison.

## The "secrets manager" concept

A secrets manager:
- **Stores:** Encrypted, versioned
- **Rotates:** On schedule
- **Audits:** Who accessed what
- **Controls:** IAM / RBAC
- **Injects:** At runtime (not in code)

The manager is the source of truth.

## The "Vault" pattern

For HashiCorp Vault:
- **KV v2:** Key-value store
- **Database:** Dynamic creds (per-request)
- **PKI:** X.509 cert issuance
- **Transit:** Encryption as service
- **SSH:** Sign keys or OTP

Vault is a secrets *service*.

## The "AWS Secrets Manager" pattern

For AWS-native:
- **KV:** JSON blob (up to 64 KB)
- **KMS:** Encrypted
- **IAM:** Scoped access
- **Lambda rotation:** Auto for RDS
- **Pricing:** $0.40/secret/mo + $0.05/10K calls

The AWS is a secrets *store*.

## The "Azure Key Vault" pattern

For Azure:
- **Standard:** $0.03/10K ops
- **Premium:** HSM-backed
- **Managed Identity:** For workloads
- **Certs:** TLS management

The Azure is cheap at scale.

## The "GCP Secret Manager" pattern

For GCP:
- **Pricing:** $0.06/version/mo + $0.03/10K accesses
- **IAM:** Per-secret
- **Versions:** Active label
- **Workload Identity:** Federation

The GCP is clean IAM.

## The "comparison" pattern

| Tool | Best for | Self-host | Key strength |
|---|---|---|---|
| Vault | Large orgs, multi-cloud | Yes | Dynamic secrets |
| AWS SM | AWS-native | No | RDS rotation |
| Azure KV | Azure-native | No | Cheap + certs |
| GCP SM | GCP-native | No | IAM + Workload ID |
| Doppler | Dev teams | No | DX + integrations |
| Infisical | OSS-first | Yes | Open source |
| Akeyless | SaaS | No | Vaultless |
| 1Password | Existing users | No | Human + dev |

The choice is per need.

## The "cost comparison" pattern

For 500 secrets, 2M calls/month:
- **Vault self-managed:** $150-300/mo + eng time
- **Vault HCP Dedicated:** $1,137/mo + secrets
- **AWS SM:** $200 + $10 = $210/mo
- **Azure KV:** $6/mo (very cheap)
- **GCP SM:** $60 + $6 = $66/mo

The cost varies by 200x.

## The "Vault vs AWS SM" decision

| Situation | Pick |
|---|---|
| AWS-only, < 1K secrets, just store + rotate | AWS SM |
| Multi-cloud, dynamic creds, PKI | Vault |
| 2 engineers, no SRE | AWS SM (managed) |
| K8s everywhere, CSI injection | Vault |
| Audit granularity critical | Vault |
| Native RDS rotation | AWS SM |
| < 200 secrets, cost matters | AWS SM |
| Will need dynamic creds in 18 mo? | Vault now |

The decision is per situation.

## The "alternating users" rotation pattern

For RDS rotation:
- **Two users:** user_v1 + user_v2
- **Alternate:** Switch on rotation
- **Why:** No window where old is invalid
- **Period:** 30 days for prod

The rotation is safe.

## The "version labels" pattern

For versioning:
- **CURRENT:** Active
- **PREVIOUS:** Old, still valid during grace
- **Rollback:** Just relabel

The versions are tracked.

## The "rotation intervals" pattern

For rotation:
- **DB creds:** 30 days prod, 90 days non-prod
- **API keys:** 90 days
- **TLS certs:** 90 days
- **Service account:** 30 days (prefer workload ID)
- **KMS keys:** Annually

The intervals are by type.

## The "workload identity" pattern

For avoiding long-lived:
- **Use:** OIDC token from cloud
- **Map:** To Vault/AWS role
- **Result:** No static keys

The identity is federated.

## The "Vault migration" pattern

For Vault:
1. **Deploy Vault:** HCP or self-managed
2. **Mirror secrets:** AWS SM → Vault (parallel)
3. **Update apps:** Vault SDK or Agent
4. **Dual-read:** 1-2 weeks both serve
5. **Cutover:** Switch to Vault only
6. **Revoke IAM:** Remove Secrets Manager perms
7. **Add dynamic:** Database, PKI engines

The migration is phased.

## The "K8s + Vault" pattern

For Kubernetes:
- **Vault Agent Injector:** Sidecar
- **CSI Driver:** Mount as volume
- **Auth:** K8s service account
- **Result:** No env vars, no files

The K8s is integrated.

## The "rotation failure" pattern

For rotation:
- **#1 cause:** Lambda failures
- **Fix:** Test in non-prod first
- **Monitor:** Rotation success rate
- **Alert:** On failure

The rotation is tested.

## The "secrets in git" anti-pattern

For secrets in git:
- **Issue:** Permanent exposure
- **Detection:** gitleaks, truffleHog
- **Fix:** Rotate, scrub, prevent
- **Prevent:** Pre-commit hook

The git is not the store.

## The ".env file" anti-pattern

For .env:
- **Issue:** Plaintext, sync conflicts
- **Fix:** Use secrets manager
- **Migration:** Doppler/Infisical

The .env is replaced.

## The "no rotation" anti-pattern

For no rotation:
- **Issue:** Compromised forever
- **Fix:** Automated rotation
- **Period:** Per type

The rotation is required.

## The "shared secrets" anti-pattern

For shared:
- **Issue:** Hard to rotate
- **Fix:** Per-user / per-service
- **Result:** Audit trail

The secrets are per identity.

## The "secret sprawl" anti-pattern

For sprawl:
- **Issue:** Secrets in many places
- **Audit:** .env, CI, K8s, TF, configs
- **Fix:** Centralize

The secrets are centralized.

## The "no audit" anti-pattern

For no audit:
- **Issue:** Can't trace access
- **Fix:** Manager logs to SIEM
- **Monitor:** All access

The audit is required.

## The "secrets manager checklist" pattern

For a checklist:
- [ ] All secrets in manager (not .env)
- [ ] Rotation enabled (per type)
- [ ] Workload identity preferred
- [ ] Audit logs to SIEM
- [ ] Pre-commit gitleaks hook
- [ ] No secrets in TF state
- [ ] K8s via CSI / Agent (not env)
- [ ] Test rotation in non-prod
- [ ] Alert on rotation failure

The checklist is comprehensive.

## Verification
- **Test:** Secrets are in manager
- **Test:** Rotation works
- **Test:** Audit logs are flowing
- **Live:** No secrets in git
- **Audit:** Quarterly

## Gotchas
- **The "secrets in git" anti-pattern.** Manager.
- **The "no rotation" anti-pattern.** Rotate.
- **The "long-lived keys" anti-pattern.** Workload ID.

## Related
- `infra/secrets-rotation-runbook.md`
- `infra/iac-best-practices.md`
- `security/slsa-supply-chain.md`
- `security/owasp-top-10-2025.md`
- CloudToolStack: https://cloudtoolstack.com/blog/secrets-management-cloud-guide
- TechPlained: https://www.techplained.com/aws-secrets-manager-vs-vault
- EnvManager: https://envmanager.com/blog/best-secrets-management-tools
