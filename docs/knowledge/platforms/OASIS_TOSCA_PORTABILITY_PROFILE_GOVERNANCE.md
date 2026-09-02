# OASIS TOSCA Portability Profile Governance

## Purpose

Govern the application of the OASIS TOSCA (Topology and Orchestration Specification for Cloud Applications) portability profile so that application topology templates remain portable across TOSCA-conformant orchestrators: the profile constrains which TOSCA constructs templates may use, and governance enforces that constraint set through automated validation rather than review vigilance.

## Scope

Applies to every TOSCA service template the studio authors or consumes. Covers profile conformance validation, template reuse, and orchestrator compatibility. Does not cover orchestrator operation (covered by orchestration guidance) or the TOSCA simple profile's type system basics (covered by existing TOSCA guidance).

## Workflow

1. Adopt a named TOSCA profile version as the studio's authoring target; templates declare the profile they conform to, and orchestrators are verified against the same profile.
2. Validate every service template against the profile's conformance rules automatically in CI: templates using constructs outside the profile fail the build with the offending construct identified.
3. Maintain a studio type library: normative TOSCA types extended by studio-specific node and relationship types, versioned independently of the templates that use them.
4. Reuse types rather than redefining topology: a node type that exists in the library is used, not forked; forks require a recorded reason and a reunion plan.
5. Test template portability by exercise: deploy templates to at least two profile-conformant orchestrators in the validation pipeline where infrastructure permits, and treat single-orchestrator-only deployment as a conformance defect.
6. Track profile evolution: when OASIS publishes profile updates, review the delta, schedule migration, and keep the CI validator version pinned until migration completes.
7. Record orchestrator-specific extensions explicitly: any escape hatch beyond the profile (custom policy types, orchestrator plugins) is documented with the portability cost it imposes.

## Controls and evidence

- Profile adoption record naming the TOSCA profile version and validator used.
- CI conformance validation results per template, including failures and their resolution.
- Studio type library with versioning and fork register (fork, reason, reunion plan).
- Portability test records: templates deployed to two conformant orchestrators with outcomes.
- Extension register documenting orchestrator-specific escape hatches and their portability cost.

## Validation

- Run the profile validator over all service templates and confirm zero conformance failures.
- Confirm each type-library fork in the register has an active reunion plan or a documented permanent-justification.
- Sample one template and confirm it deploys to both target orchestrators from the same artifact.

## Failure correction

- **Template fails profile validation** → fix the construct or justify and record a profile exception; unrecorded exceptions are build failures.
- **Portability test fails on second orchestrator** → fix the template divergence or the type library, then re-run both deployments.
- **Type library fork drifting** → merge upstream changes into the fork or absorb the fork; drifting forks are removed from the library.

## Limitations

- Profile conformance improves portability but does not guarantee semantic equivalence across orchestrators; runtime behavior still needs testing on each target.
- TOSCA ecosystem tooling maturity varies; validator coverage may lag the specification.
- The portability exercise requirement needs at least two orchestrators available; where only one exists, document the limitation and validate statically.

## Scope note

This article is part of the platforms leaf. Cross-reference: `OASIS_TOSCA_SIMPLE_PROFILE_GOVERNANCE.md`, `ETSI_NFV_MANAGED_SERVICE_GOVERNANCE.md`, and `CNCF_FLUX_GITOPS_RECONCILIATION_GOVERNANCE.md` (operations leaf).

## Canonical sources

- OASIS — TOSCA Simple Profile in YAML Version 1.3: https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.3/TOSCA-Simple-Profile-YAML-v1.3.html
- OASIS — TOSCA Version 2.0: https://docs.oasis-open.org/tosca/TOSCA/v2.0/TOSCA-v2.0.html
- OASIS — TOSCA elevation to OASIS Open (CAMP/TOSCA interoperability): https://www.oasis-open.org/committees/tosca/
- ISO/IEC 22123-3:2023 — Cloud computing — Part 3: Interoperability: https://www.iso.org/standard/85749.html
- NIST SP 800-145 — The NIST Definition of Cloud Computing: https://csrc.nist.gov/publications/detail/sp/800-145/final
