# NIST SP 800-90B:2024 Entropy Source Governance

## Purpose

NIST SP 800-90B, "Recommendation for the Entropy Sources Used for Random Bit Generation," provides guidance on designing, testing, and validating entropy sources used in random bit generation (RBG). The publication defines the entropy source model, the noise sources, the conditioning, the health tests, and the documentation requirements. This article governs the application of SP 800-90B so entropy sources in random bit generators produce entropy of the quality required for cryptographic use.

## Scope

The publication applies to any organization using entropy sources for random bit generation. Within this knowledge base, the article covers the entropy source model (noise source, conditioning, output), the noise sources (physical, non-physical), the entropy assessment, the health tests, the documentation, and the validation against the publication. It does not cover the construction of an RBG (SP 800-90A) or the use of an RBG in a specific application; readers should consult those publications separately.

## Workflow

1. Establish the entropy source policy: scope, noise sources used, conditioning method, health tests, and the validation requirements.
2. Select or design the entropy source:
   - Noise source: physical (ring oscillators, shot noise, thermal noise) or non-physical (system events, user input).
   - Conditioning: a vetted conditioning function per SP 800-90B/C.
3. Perform the entropy assessment: estimate the min-entropy of the noise source output. The min- entropy determines how much output the conditioning function needs to produce the desired entropy at the output.
4. Implement health tests:
   - Startup test: confirm the entropy source produces expected output at startup.
   - Continuous tests: detect deviations from the expected behavior during operation.
5. Document the entropy source: the design, the assessment, the conditioning, the health tests, and the validation.
6. Validate the entropy source per the publication's validation requirements (typically via NIST's Cryptographic Module Validation Program or equivalent).

## Controls and evidence

Entropy source controls include the documented design, the entropy assessment, the conditioning, the health test records, and the validation evidence. Each entropy source should be traceable from its noise source through the conditioning to its output.

## Validation

Validation should confirm the entropy source design is documented, the min-entropy assessment is performed, the conditioning is vetted, the health tests detect deviations, and the source has been validated per the publication. Periodic re-assessment confirms the source remains at the expected entropy level.

## Failure correction

Common failure modes: the entropy assessment is overestimated (correct: use the conservative estimator the publication describes); health tests are not implemented (correct: implement startup and continuous tests); the entropy source is not validated (correct: pursue validation per the publication); the conditioning function is not vetted (correct: use a vetted function per SP 800-90B/C).

## Limitations

NIST SP 800-90B provides guidance; it does not certify any entropy source. The validation is typically performed by a CMVP-accredited lab as part of the module validation. The publication does not address every noise source; readers should consult the publication's supplements for specific source types.

## Scope note

This article summarizes project-neutral reference use of NIST SP 800-90B. It does not assert any specific entropy source's conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-90B — Recommendation for the Entropy Sources Used for Random Bit Generation: https://csrc.nist.gov/publications/detail/sp/800-90b/final