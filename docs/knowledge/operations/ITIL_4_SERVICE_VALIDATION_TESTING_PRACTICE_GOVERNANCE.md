# ITIL 4 Service Validation and Testing Practice Governance

## Purpose

The ITIL 4 Service Validation and Testing practice ensures that new or changed services meet the requirements and the design's quality characteristics before they are released to users. The practice operates alongside the transition planning and change management practices. This article governs the application of the Service Validation and Testing practice so services are validated and tested against the design and the service acceptance criteria before release.

## Scope

The practice applies to the validation and testing of new or changed services. Within this knowledge base, the article covers the validation activities (acceptance testing, operational readiness testing, performance testing, security testing, user acceptance testing), the test environment, the test data, the test records, and the documentation of validation outcomes. It does not cover production testing, A/B testing, or the broader release engineering discipline; readers should consult those separately.

## Workflow

1. Define the validation and testing approach: the test scope, the test types (functional, performance, security, usability, accessibility), the test environments, the test data, the acceptance criteria, and the responsibilities.
2. Develop the test plan and test cases from the service design package and the service requirements. Each acceptance criterion should map to at least one test case.
3. Set up the test data: production-equivalent but appropriately anonymized where the data is sensitive.
4. Execute the tests in the test environment that mirrors production as closely as possible. Capture the results, the defects, and the evidence.
5. Conduct user acceptance testing with representatives of the user community.
6. Conduct operational readiness testing: confirm the service can be deployed, monitored, supported, and recovered by the operations team.
7. Document the validation outcome: the test results, the defects found, the defects deferred, and the residual risks.
8. Approve the service for release based on the validation outcome against the acceptance criteria.

## Controls and evidence

Validation evidence includes the test plan, the test cases, the test results, the defect records, the user acceptance sign-off, the operational readiness sign-off, and the validation report. The validation report should clearly state whether the service meets the acceptance criteria and the conditions of release.

## Validation

Validation should confirm the test plan covers all acceptance criteria, the test cases are aligned with the design, the test environment is production-equivalent, the test data is appropriate, defects are tracked, and the validation outcome supports the release decision. Independent review of the validation report provides additional assurance.

## Failure correction

Common failure modes: tests do not cover all acceptance criteria (correct: trace each criterion to test cases); test environment differs significantly from production (correct: reduce environment differences and document their impact); user acceptance is performed by project members rather than users (correct: require user representative participation); defects are tracked but not resolved (correct: gate release on defect status with explicit accept-with-risk); operational readiness is assumed (correct: test the operational procedures in the test environment).

## Limitations

ITIL 4 is a guidance framework; it does not prescribe specific test tools or environments. The Service Validation and Testing practice must be integrated with the organization's broader test strategy and with the change management practice.

## Scope note

This article summarizes project-neutral operations use of ITIL 4 Service Validation and Testing. It does not assert any specific organization's validation and testing conformance or claim any certification outcome.

## Canonical sources

- AXELOS — ITIL 4 Foundation and Managing Professional streams: https://www.axelos.com/certifications/itil-service-management