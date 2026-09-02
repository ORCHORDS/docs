# NIST SP 800-131A:2024 Cryptographic Algorithm Transition Governance

## Purpose

NIST SP 800-131A, "Recommendation for Cryptographic Algorithm and Key Length Transitions," provides guidance on transitioning from deprecated cryptographic algorithms and key lengths to current ones. The publication lists algorithms that NIST considers acceptable, deprecated, or disallowed, and provides transition timelines for each. This article governs the application of SP 800-131A so the organization's cryptographic inventory moves to current algorithms in a planned way.

## Scope

The publication applies to any organization using cryptographic algorithms. Within this knowledge base, the article covers the algorithm classifications (acceptable, deprecated, disallowed), the transition timelines, the cryptographic inventory, the migration plan, and the documentation of the cryptographic posture. It does not cover every cryptographic algorithm (the publication addresses NIST-approved algorithms); readers should consult the publication for the latest classifications.

## Workflow

1. Maintain a cryptographic inventory: the algorithms used, the keys, the protocols, the implementations, and the lifecycle status.
2. Classify each algorithm against the publication's classifications:
   - Acceptable: the algorithm may be used.
   - Deprecated: the algorithm may be used only for legacy interop, with a transition plan.
   - Disallowed: the algorithm must not be used.
3. For each deprecated or disallowed algorithm, plan the transition:
   - Identify the uses of the algorithm in protocols, libraries, and systems.
   - Select the replacement algorithm and protocol.
   - Plan the migration in stages (lab, staging, production).
   - Coordinate with external parties that depend on the deprecated algorithm.
4. Execute the migration with testing and verification. Maintain backward compatibility for legacy interop as long as necessary.
5. Update the cryptographic inventory and the documentation.

## Controls and evidence

Transition controls include the cryptographic inventory, the transition plan, the migration records, the testing and verification records, and the post-migration review. Each algorithm should be traceable from inventory through migration to its replacement.

## Validation

Validation should confirm the inventory is current, the transition plan is documented and tracked, the migration is tested before production deployment, the deprecated algorithm is removed where possible, and the replacement operates correctly. Periodic audits confirm the cryptographic posture remains aligned with the publication.

## Failure correction

Common failure modes: the inventory is incomplete (correct: maintain a comprehensive inventory of algorithms, keys, and protocols); deprecated algorithms are not migrated (correct: prioritize migration based on the publication's timelines and the organization's risk); migration is done without testing (correct: test the migration in non-production before production); legacy interop is used as a permanent workaround (correct: document the legacy interop, set a sunset, and migrate).

## Limitations

NIST SP 800-131A provides transition guidance for NIST-approved algorithms; it does not address every algorithm used in practice. The publication does not certify any cryptographic inventory; the organization's conformance is determined by its ability to demonstrate the inventory and the migration. Sector regulations may impose specific transition timelines.

## Scope note

This article summarizes project-neutral reference use of NIST SP 800-131A. It does not assert any specific cryptographic inventory's conformance or claim any certification outcome.

## Canonical sources

- NIST SP 800-131A — Recommendation for Cryptographic Algorithm and Key Length Transitions: https://csrc.nist.gov/publications/detail/sp/800-131a/rev-2/final