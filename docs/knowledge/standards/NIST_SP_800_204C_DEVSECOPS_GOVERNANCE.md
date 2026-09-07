# NIST SP 800-204C Implementation of DevSecOps for a System-of-Systems Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST Special Publication 800-204C, "Implementation of DevSecOps for a System-of-Systems". It applies to engineering organisations building composed platforms where multiple independently-deployable services share a CI/CD pipeline, security tooling, and runtime telemetry surface.

## 2. Normative references

- NIST SP 800-204C, Revision 1 (2024).
- NIST SP 800-204 (security strategies for microservices).
- NIST SP 800-218 Rev. 1.1 (SSDF) for foundational practices.
- CNCF TAG-Security whitepaper on supply-chain security.

## 3. System-of-systems (SoS) composition principles

1. **Autonomy**: each constituent system retains its own release cadence; the SoS-level pipeline composes but does not gate individual deliveries beyond declared interface contracts.
2. **Belonging**: every constituent system publishes a CycloneDX SBOM, a Cosign-signed OCI artefact, and a SLSA Level 3 provenance attestation to the SoS evidence store.
3. **Connectivity**: cross-system interfaces MUST be described in a versioned OpenAPI/AsyncAPI document and validated by contract tests in CI.
4. **Diversity**: at least two independent implementations are required for any cross-cutting capability (logging, secret management, identity) — see NIST 800-204C §4.2.

## 4. DevSecOps control gate matrix

| Phase | Gate | Evidence | Owner |
| --- | --- | --- | --- |
| Plan | Threat model updated | `threat-model.json` link + reviewer sign-off | Service team |
| Code | Secret scanning clean | Gitleaks/Trivy output | Security Eng |
| Build | SBOM + signed artefact | Cosign signature + Syft SBOM | Build Eng |
| Test | SAST/DAST/SCA green | SARIF artefacts merged into DefectDojo | AppSec |
| Release | Provenance attestation | in-toto v1 predicate | Build Eng |
| Deploy | Admission policy pass | Conftest/Conftest-OPA report | Platform |
| Operate | SLOs published | SLI/SLO doc in `engineering/slos/` | SRE |
| Respond | Incident runbook tested | Quarterly gameday outcome | Incident Mgr |

## 5. Policy enforcement

- Gates are codified as Tekton/Argo Workflows tasks; manual override requires an ADR + Security Council approval with a 30-day sunset.
- "Stage gate" terminology aligns with NIST 800-204C §5 and supersedes any internal-only stage naming.

## 6. Measurement

- Track **leading** indicators: % pipelines with all 8 phases gated, time-to-restore, change-failure-rate.
- Track **lagging** indicators: production incidents attributable to gate bypass, post-deploy vulnerability escape rate.

## 7. Exceptions

Any deviation from §4 requires a written exception registered in `policies/exceptions/` with a mitigation plan and an expiry date no later than the next review cycle.

## 8. Review cadence

This card is reviewed every 180 days by Knowledge Engineering, with the next review on 2027-03-06. Significant NIST revisions trigger an out-of-cycle update.
