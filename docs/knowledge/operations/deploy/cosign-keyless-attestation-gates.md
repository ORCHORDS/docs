# Cosign Keyless Attestation Gates

**Issue:** Cosign signs and verifies container images using OCI registries as the signing substrate, and the keyless mode binds a signature to an OIDC identity rather than to a long-lived private key. Teams that adopt keyless signing without understanding how the OIDC-to-Fulcio-to-Rekor pipeline produces a verifiable attestation cannot reason about what the gate is actually checking when it admits an image.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Keyless Signing Components

Keyless signing is implemented by three cooperating services: Fulcio is the certificate authority that issues short-lived certificates bound to an OIDC identity (typically a CI runner's identity token from GitHub Actions, GitLab CI, or similar). Rekor is the transparency log that records every signing event and produces an immutable, publicly auditable record of what was signed and by whom. Cosign is the client that orchestrates the request to Fulcio, the signature computation, and the submission to Rekor, all in a single command.

The output of the signing flow is a cosign signature stored in the registry alongside the image, plus a Rekor entry stored in the Rekor log. The signature contains a certificate whose Subject Alternative Name carries the OIDC identity, and the certificate is signed by Fulcio's intermediate CA. Anyone holding the Fulcio root can validate the certificate; anyone with access to the Rekor log can verify the signature was recorded. The two together produce a strong binding between identity and signature.

## Policy Enforcement With Connaisseur Or Kyverno

Policy enforcement is typically implemented as an admission controller that intercepts pod creation requests and verifies the image signature before admitting the workload. Connaisseur is a CNCF Sandbox project that does specifically this: it watches pod requests, resolves the image reference to a digest, fetches the signature from the registry, verifies against configured public keys or Fulcio roots, and admits only on success. Kyverno can also be configured to verify cosign signatures via its `verifyImages` rule.

The policy must specify what counts as a valid signer. Keyless mode permits filtering by the OIDC identity embedded in the certificate; for example, "admit only images signed by GitHub Actions workflows running in the example-org/example-repo repository". The filter is expressed as a regex on the certificate's SAN, matched against the certificate's `Identity` or `Issuer` fields. A permissive filter accepts too many signatures; a restrictive filter may reject legitimate builds because the OIDC identity changed slightly.

## Rekor Inclusion Proof Verification

A signature is verifiable against Rekor via an inclusion proof: the signature includes the SHA-256 hash of a Rekor entry, and the entry's Merkle tree inclusion proves the entry was committed to the log at a specific tree size. The inclusion proof can be verified offline by anyone holding the log's public key. This is what makes Rekor a transparency log rather than just a database: the inclusion proof is a cryptographic commitment that the entry cannot be retroactively modified.

Operators should run their own Rekor instance when the verification policy demands isolation from the public Sigstore Rekor. Self-hosted Rekor requires its own signing key and storage backend; the trade-off is that verification offline becomes impossible without access to the local instance. Many teams accept the public Rekor because the inclusion proof is the authoritative artifact; the Rekor instance itself is just the storage layer.

## Attestation Predicates Beyond Existence

Cosign supports attaching arbitrary attestations to images via `cosign attest`. The attestation is a signed statement with a typed predicate; Syft SBOMs are one predicate type, SLSA provenance is another, vulnerability scan results are a third. Each attestation has its own OIDC identity, its own signing path, and its own inclusion in Rekor. Verification of an attestation is the same flow as verification of a signature: fetch, verify, check predicate contents against policy.

Predicates enable richer gate logic. An admission policy can require not just a signature but an SBOM attestation, a vulnerability scan attestation, and a build provenance attestation. The gate runs each verification in turn, and the workload is admitted only if all three pass. The audit trail is the union of the three Rekor entries, each one documenting the predicate's content at signing time.

## Failure Modes

The most damaging failure is the admission controller configured to verify signatures but not identities. The default cosign policy accepts any valid signature against the Fulcio root, which means any OIDC identity can sign images that pass the gate. An attacker who can trigger a signing operation against any CI workflow anywhere on the public internet can produce a signature that the gate accepts. Always pair signature verification with identity verification; the SAN filter is the policy that prevents this failure.

A second failure is Rekor unavailability. If Rekor is down or unreachable, the inclusion proof cannot be verified, and a strict gate will reject all images. Operators who interpret the rejection as a transient failure may bypass the gate to ship an emergency fix, undermining the entire attestation model. Configure the gate to fail closed on Rekor unavailability and use cached inclusion proofs for graceful degradation; the cached proofs must be short-lived, and the cache must be populated from a recent Rekor fetch.

A third failure is key rotation in the OIDC provider. When the provider rotates signing keys, the Fulcio certificates issued under the old key become unverifiable against the new key. The gate may suddenly start rejecting images whose builds were legitimately signed under the old key. Configure the gate to accept the previous provider key for a transition window, and reissue the gate's trust anchors whenever the provider rotates.

## Canonical sources

1. https://docs.sigstore.dev/cosign/keyless/
2. https://docs.sigstore.dev/verify/