# Agent Model Provenance Attestation

## Scope

This article covers cryptographic and metadata attestations that bind an agent runtime output to the specific model identifier, version, and configuration that produced it. Model provenance is the chain of evidence from a model output back through the model artifact, the build that produced the artifact, the source materials that went into training or fine-tuning, and the configuration in which the model was loaded at inference time. The article covers what to attest, how to attest it, and how consumers of an agent's output can verify the attestation.

Out of scope: model evaluation against benchmarks (which is a separate discipline covered in this family's evaluation articles), full SLSA-level supply-chain provenance for the model artifact itself (which is a prerequisite but not the focus here), and the legal or contractual aspects of model provenance (which are policy questions).

## Implementation workflow

At model load time, the runtime computes a model identifier that is unique to the deployed artifact. The identifier includes the model family, the version string provided by the model publisher, the quantization or format identifier, the hash of the model artifact (typically a SHA-256 over the canonical bytes), and the hash of any adapter or fine-tuning weights that were applied on top. The identifier is the foundation of the attestation; every later attestation step references it.

The runtime also captures the configuration: the inference parameters in effect at the time of the call (temperature, top-p, max tokens, stop sequences), the system prompt and prompt template version, the tool manifest, and the runtime version. The configuration is captured per call rather than globally, because a runtime that supports hot-swapping models or per-tenant configuration must attest to the specific configuration of each call.

The attestation is signed at the moment of inference. The signing key is bound to the workload through a workload identity attestation such as SPIFFE; the attestation document references the workload identity, the model identifier, the configuration, the input reference (a hash of the prompt or input bundle), and a sequence number. The signing operation is local to the runtime and must not be delegated to an external service, because the attestation's value derives from the runtime's ability to assert what it actually used.

The attestation is delivered alongside the output. Consumers — downstream agents, audit pipelines, or human reviewers — receive the attestation document and can verify it independently. The verification checks the signature against the workload's published identity, the freshness of the attestation against the configured maximum age, the model identifier against an allow-list maintained by the consumer, and the configuration against any policy the consumer applies.

For long-running agent workflows, attestations accumulate. Each call to the model produces an attestation; the agent's overall decision is the result of a chain of model calls, each with its own attestation. The chain is structured as a Merkle-like hash chain: each attestation references its predecessor by hash, so that tampering with any earlier attestation is detectable. This pattern is consistent with the IETF SCITT working group's approach to transparency for supply-chain attestations.

## Controls

Model identifiers must be unambiguous. Two model artifacts that differ in any byte must have different identifiers, and two artifacts that are byte-identical must produce the same identifier regardless of where they are loaded. The identifier is computed as a canonical hash; loading the same artifact twice produces the same hash. This discipline prevents a malicious or buggy runtime from substituting one model for another while keeping the same identifier.

Attestation keys are workload-bound. The signing key is provisioned to the workload through an attestation-based key delivery protocol (such as the SPIFFE workload API); the key is not shared across workloads and is rotated according to a policy that balances freshness against operational overhead. A leaked key must be detectable through the key delivery protocol's revocation list.

Verify before trust. Consumers must not accept an attestation without verification. The verification checks the signature, the freshness, the model identifier allow-list, and the configuration against policy. A consumer that processes attestations without verification is not actually relying on provenance; it is only logging metadata. The verification step must be implemented in the consumer's runtime, not in the agent's runtime, so that the two are independent.

Confidentiality of attestation content. Attestations may include sensitive information (such as a hash of a confidential prompt); consumers are responsible for protecting attestation confidentiality at the level appropriate to their threat model. Public attestation registries, where they exist, must redact or hash sensitive fields.

## Validation evidence

Conformance tests must cover: model identifier computation is canonical (same artifact produces same identifier), different artifacts produce different identifiers, configuration is captured per call and reflected in the attestation, signature verification passes for genuine attestations and fails for tampered ones, freshness checks reject stale attestations, allow-list enforcement rejects unknown model identifiers, hash chain detects tampering with any earlier attestation, and the signing key cannot be used by another workload. Inject a swapped model artifact and verify the attestation exposes the swap.

Operational evidence includes: distribution of model identifier hashes, attestation signature verification success rate, count of att rejected for freshness, count rejected for allow-list mismatch, count rejected for signature failure, and chain-integrity check success rate. Attestation verification telemetry is itself subject to monitoring; a verification success rate that is suspiciously high or low is an alertable anomaly.

## Failure handling

When the signing key is unavailable or has been revoked, the runtime must refuse to issue new attestations and must halt any workflow that requires attestations to proceed. A workflow that proceeds without attestation would create outputs that cannot be traced to a model identifier; this is a fail-closed posture.

When an attestation verification fails on the consumer side, the consumer does not silently discard the output. The consumer records the failure, retains the output under quarantine, and notifies the operator. The decision to discard or to escalate is a human judgment; the consumer's role is to preserve the evidence that the verification failed.

When a model identifier is discovered to be ambiguous or hash-collision-vulnerable, the runtime must update its identifier algorithm in a coordinated way across all workloads. Existing attestations remain valid under their original algorithm; new attestations use the new algorithm. The transition is documented in the model's provenance record.

When an attestation chain is broken (for example, when an attestation in the middle of the chain cannot be retrieved), the agent pauses the downstream decision, surfaces a `provenance-gap` error, and either re-runs the missing steps or escalates. The agent does not proceed on the assumption that a missing attestation is benign.

## Canonical sources

- IETF SCITT (Supply Chain Integrity, Transparency and Trust) working group documents: https://datatracker.ietf.org/wg/scitt/about/
- NIST SP 800-204D, Implementation of DevSecOps for a Microservices-based Application with Service Mesh (background reference for artifact attestation patterns): https://csrc.nist.gov/pubs/sp/800/204/d/final
- W3C Verifiable Credentials Data Model 2.0 (background reference for cryptographic attestation structure): https://www.w3.org/TR/vc-data-model-2.0/
- Cloud Native Computing Foundation, SPIFFE Workload Identity specification: https://github.com/spiffe/spiffe/blob/main/standards/SPIFFE.md
