# Agent Software Supply Chain Evidence with SLSA Provenance

## Purpose

An agent deployment can combine runtime code, prompts, policy bundles, tool adapters, model configuration, and container images. Security review needs evidence about how those artifacts were produced and whether the deployed bytes match reviewed inputs. SLSA defines a supply-chain framework and a provenance format for describing where, when, and how an artifact was built. in-toto defines the attestation envelope and statement model commonly used to carry such claims.

Provenance is evidence, not a declaration that software is safe. It can support verification that an artifact came from an expected builder and source revision under stated build parameters. A consumer still needs an explicit policy describing which builders, repositories, dependencies, and build properties are acceptable.

## Implementation workflow

1. Enumerate deployable agent artifacts and choose immutable subjects for provenance, normally cryptographic digests of images, packages, binaries, and signed policy bundles. Do not rely on mutable tags.
2. Use an automated build platform with an authenticated builder identity. Keep provenance generation in the build control plane rather than allowing the build script to invent evidence about itself.
3. Emit SLSA provenance using the defined provenance predicate. Include the artifact subject, build definition, resolved dependencies available to the builder, builder identity, invocation information, and relevant timestamps according to the predicate schema.
4. Wrap the statement in the selected in-toto attestation format and sign it using the organization’s approved mechanism. Store the attestation beside the artifact in a registry or evidence service that preserves digest association.
5. At admission or deployment time, resolve the candidate artifact to a digest, retrieve its attestations, verify signatures and trust roots, validate the statement and predicate types, and evaluate local policy.
6. Record the verification result and exact subject digest. Deployment manifests should pin that digest so later tag movement cannot substitute different bytes.

Prompts or configuration files should be included only with clear artifact boundaries. They may be packaged and digested as a release bundle, or separately attested if they have independent lifecycles. Avoid claiming that SLSA natively evaluates prompt quality or model behavior; it describes supply-chain properties.

## Controls

Separate build authority from source-change approval and deployment authority. Restrict who can configure trusted builders and verification policy. The verifier must reject an attestation whose subject digest does not equal the candidate artifact, even if its signature is valid. It must also reject unrecognized predicate types, malformed statements, untrusted signers, and builder identities outside policy.

Evaluate provenance fields semantically. Confirm the source repository and revision, expected build workflow, and material dependencies where policy requires them. Treat user-controlled build parameters as inputs, not endorsements. Protect against downgrade by requiring the intended provenance predicate and policy level rather than accepting any signed envelope.

Retain transparency-log inclusion or signing-system evidence when the chosen signing architecture provides it. Keep trust-root rotation and revocation procedures. Do not place credentials or sensitive build arguments in provenance because attestations may be broadly visible.

## Validation and evidence

Create a golden-path build and verify its artifact digest, signature, statement type, predicate schema, builder identity, and source revision. Then run negative tests: modify the artifact after build, point a tag to a different digest, sign with an untrusted key, alter the source reference, omit required fields, and submit an unsupported predicate. Admission should reject each case for a specific reason.

Reproduce a sample build where practical and compare outputs or explain nondeterministic fields. Reproducibility is useful corroboration but is not automatically guaranteed by provenance. Keep build logs, immutable source revision, artifact digest, attestation, signature-verification output, admission decision, and deployment digest as the evidence chain.

## Failure handling

If provenance is missing, unverifiable, or inconsistent, quarantine the artifact and stop promotion. An emergency exception should be time-limited, explicitly approved, logged, and followed by retrospective evidence generation only if the resulting statement accurately describes the original build; never fabricate provenance after the fact.

If a trusted builder or signing identity is compromised, revoke or distrust it, identify all artifacts attested by that identity during the affected period, and reassess or rebuild them on a known-good builder. If the deployed digest differs from the verified subject, treat this as an admission or registry integrity failure and roll back to a verified digest while preserving forensic records.

## Canonical sources

- SLSA, *Supply-chain Levels for Software Artifacts specification*: https://slsa.dev/spec/
- SLSA, *Provenance*: https://slsa.dev/spec/v1.0/provenance
- in-toto, *Attestation Framework*: https://github.com/in-toto/attestation/blob/main/spec/README.md
- in-toto, *Statement specification*: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md
