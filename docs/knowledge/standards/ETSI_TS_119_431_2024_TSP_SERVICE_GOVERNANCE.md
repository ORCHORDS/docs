# ETSI TS 119 431:2024 TSP Service Components Governance

## Purpose

ETSI TS 119 431:2024, "Electronic Signatures and Infrastructures (ESI); Policy and security requirements for trust service components," defines the policy and security requirements for the components that TSPs use to deliver their trust services. The technical specification addresses the responsibilities of TSP component providers, the assessment of components for use in TSP operations, and the documentation of the component's security properties. This article governs the application of TS 119 431 so a TSP's component selection and assessment is aligned with the standard.

## Scope

The technical specification applies to TSPs and to providers of trust service components (e.g., HSM providers, time-stamping authorities, CA software providers). Within this knowledge base, the article covers the component categories, the security requirements, the assessment framework, and the documentation of component selection and assessment. It does not cover the substantive security properties of any specific component; readers should consult the component's documentation.

## Workflow

1. Identify the trust service components the TSP uses: HSMs, CA software, time-stamping software, signature creation devices, and other components.
2. Apply the standard's framework to each component:
   - Identify the security requirements the component must meet.
   - Determine the appropriate assessment level based on the component's role in the trust service.
   - Document the assessment: the security target, the evaluation level, the evaluation results, and the residual risks.
3. Operate the component per the documented configuration and the security target.
4. Maintain the assessment: re-evaluate on component changes, on changes to the trust service, and on changes to the security environment.
5. Document the component selection, the assessment, the operation, and the maintenance.

## Controls and evidence

Component controls include the documented selection, the assessment records, the security target, the configuration records, and the maintenance records. Each component should be traceable from selection through assessment to operation.

## Validation

Validation should confirm the components are assessed at the appropriate level, the security targets are current, the configuration matches the documentation, and the maintenance discipline operates. Periodic re-assessment confirms the components remain fit for purpose.

## Failure correction

Common failure modes: components are used without assessment (correct: assess each component before use); the assessment is one-time (correct: re-assess on changes); the security target is aspirational (correct: ground the security target in the actual configuration); components are configured outside the security target (correct: enforce the configuration per the security target).

## Limitations

ETSI TS 119 431 provides a framework for component assessment; it does not certify any specific component. The technical specification does not replace the component's certification (e.g., Common Criteria, FIPS 140-3); readers should consider both. The standard does not address every component type; readers should consult the appropriate technical specification for each.

## Scope note

This article summarizes project-neutral standards use of ETSI TS 119 431:2024. It does not assert any specific TSP's or component provider's conformance or claim any certification outcome.

## Canonical sources

- ETSI TS 119 431:2024 — Policy and security requirements for trust service components: https://www.etsi.org/deliver/etsi_ts/119400_119499/119431/