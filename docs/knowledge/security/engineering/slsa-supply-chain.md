# slsa-supply-chain

**Issue:** SLSA — Supply-chain Levels for Software Artifacts
**Date:** 2026-08-09
**Status:** documented

## Symptom
A dependency was compromised. The build was tampered
with. The artifact is malicious. You deploy it.
Production is pwned. You wish you had provenance.

## Root cause
**Software supply chains are attack targets.** Use
SLSA + Sigstore.

**Source:** SLSA:
https://slsa.dev

## The "SLSA" concept

SLSA ("salsa") is a security framework for build
integrity:
- **Provenance:** Verifiable evidence of build
- **Levels:** L1, L2, L3 (ascending)
- **Build track:** Stable
- **Source track:** In development

The framework is graduated.

## The "L1: provenance exists" pattern

For L1:
- **Build:** Fully scripted (no manual)
- **Provenance:** Auto-generated
- **Signed:** No
- **Hosted:** No
- **What it stops:** Accidental misconfig

The provenance is emitted.

## The "L2: signed provenance" pattern

For L2:
- **Build:** Hosted CI/CD
- **Provenance:** Auto + signed
- **What it stops:** Hand-forged provenance
- **Effort:** Medium (move to hosted signed builds)

The provenance is signed.

## The "L3: hardened build" pattern

For L3:
- **Build:** Isolated + ephemeral
- **Signing:** Secrets inaccessible to build steps
- **Provenance:** Cannot be falsified
- **What it stops:** SolarWinds-class attacks
- **Effort:** Higher (hardened runners)

The build is hardened.

## The "in-toto attestation" pattern

For provenance format:
```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{
    "name": "my-artifact",
    "digest": {"sha256": "abc123..."}
  }],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://github.com/slsa-framework/slsa-github-generator",
      "externalParameters": {
        "repository": "https://github.com/org/repo",
        "ref": "refs/heads/main"
      }
    },
    "runDetails": {
      "builder": {
        "id": "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml"
      }
    }
  }
}
```

The format is in-toto.

## The "in-toto envelope" pattern

For the envelope:
- **DSSE:** Dead Simple Signing Envelope
- **Statement:** Subject + predicateType
- **Predicate:** Payload (SLSA, SBOM, etc.)
- **URI dispatch:** Verifier reads predicateType

The envelope is layered.

## The "Sigstore" pattern

For signing:
- **Cosign:** Sign artifacts
- **Fulcio:** Short-lived OIDC certs
- **Rekor:** Transparency log
- **Keyless:** No long-lived keys
- **Verify:** `--certificate-identity-regexp`

The signing is keyless.

## The "verification workflow" pattern

For verification:
1. **Download:** Artifact + provenance
2. **Verify signature:** Against Sigstore CT log
3. **Check builder:** Matches trusted builders
4. **Verify digest:** Matches artifact
5. **Validate source:** Repo + commit match
6. **Policy engine:** Approve or reject

The verification is automated.

## The "cosign verify" pattern

For verification:
```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/org/repo" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/org/image:tag
```

The cosign verifies.

## The "L1 migration" pattern

For L1:
- Script all builds
- Auto-generate provenance
- Store with artifacts

The L1 is a starting point.

## The "L2 migration" pattern

For L2:
- Move to hosted CI/CD
- Sign with Sigstore
- Verify in staging

The L2 is the target.

## The "L3 migration" pattern

For L3:
- Isolated runners
- Ephemeral envs
- Signing secrets outside build
- Enforce in prod

The L3 is for high-risk.

## The "SBOM" pattern

For SBOM (Software Bill of Materials):
- **Format:** SPDX, CycloneDX
- **Required for:** Government, EU CRA
- **Generate:** Syft, cdxgen
- **Attach:** To every artifact

The SBOM is required.

## The "supply chain threat model" pattern

For threats:
- **Compromised dep:** Lock file + SBOM
- **Tampered source:** Commit signing
- **Compromised CI:** SLSA L3 + isolated
- **Forged artifact:** Signature + provenance
- **Dependency confusion:** Pin by digest
- **Typosquatting:** Use trusted registry

The threats are modeled.

## The "verify at deploy" pattern

For deployment:
```yaml
# Kubernetes admission controller
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: slsa-verify
spec:
  validations:
    - expression: |
        has(object.metadata.annotations['cosign.sigstore.dev/signature']) &&
        has(object.metadata.annotations['slsa.dev/provenance'])
```

The deploy verifies.

## The "GitHub SLSA generator" pattern

For GitHub Actions:
```yaml
- uses: slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@v1.10.0
  with:
    base64-subjects: "${{ needs.build.outputs.digests }}"
```

The GitHub generator emits L3 provenance.

## The "Sigstore + Kubernetes" pattern

For K8s:
- **cosign:** Sign images
- **Connaisseur/kyverno:** Verify at admission
- **Rekor:** Transparency log
- **Fulcio:** Cert from OIDC

The K8s verifies.

## The "deny by default" pattern

For policy:
- **Default:** Deny unsigned
- **Allow:** With expiry
- **Audit:** Continuous
- **Rotate:** Keys regularly

The policy is deny-first.

## The "SLSA checklist" pattern

For a checklist:
- [ ] Generate provenance (start L1)
- [ ] Sign with cosign
- [ ] Verify with --certificate-identity-regexp
- [ ] Attach SBOM
- [ ] Reference by digest (not tag)
- [ ] Verify at CI promotion
- [ ] Verify at K8s admission
- [ ] Deny by default
- [ ] Bundle Rekor inclusion proofs

The checklist is comprehensive.

## The "SLSA + OWASP" mapping

| SLSA | OWASP |
|---|---|
| L1 | A06: Vuln Components |
| L2 | A08: Software & Data Integrity |
| L3 | A08 (high) |

The mapping is partial.

## Verification
- **Test:** Provenance is emitted
- **Test:** Signature verifies
- **Test:** Build is reproducible
- **Live:** Admission control denies
- **Audit:** Quarterly

## Gotchas
- **The "no provenance" anti-pattern.** Start at L1.
- **The "mutable tags" anti-pattern.** Reference by digest.
- **The "long-lived keys" anti-pattern.** Use Sigstore keyless.

## Related
- `security/owasp-top-10-2025.md`
- `security/owasp-api-top-10-2023.md`
- `security/security-headers-deep-dive.md`
- `github/github-actions-reusable-workflows.md`
- SLSA: https://slsa.dev
- Practical DevSecOps: https://www.practical-devsecops.com/slsa-framework-guide-software-supply-chain-security/
- IoT Digital Twin PLM: https://iotdigitaltwinplm.com/slsa-sigstore-software-supply-chain-security-architecture-2026/
