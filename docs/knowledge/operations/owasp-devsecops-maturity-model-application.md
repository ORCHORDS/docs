# OWASP DevSecOps Maturity Model Application

## Purpose

The OWASP DevSecOps Guideline (DSCF) describes a maturity model across dimensions — culture, governance, design, implementation, verification, deployment, operations, and monitoring — that organizations can use to assess their DevSecOps posture. This article summarizes the operating engineering application of the model so that platform and product teams can use it consistently across service classes. The model is descriptive and educational; it does not establish a certification.

## Dimensions

The OWASP DevSecOps Guideline organizes its dimensions around the lifecycle:

- **Culture** — the shared understanding between security, operations, and engineering of the goals and responsibilities across the lifecycle.
- **Governance** — the policies, standards, and oversight that make individual controls auditable and comparable across the portfolio.
- **Design** — practices applied before code is written: threat modeling, reference architectures, secrets handling, and design review.
- **Implementation** — secure-coding practices, code review, dependency controls, and framework or library selection.
- **Verification** — automated testing, manual review, red-team engagement, and assurance review.
- **Deployment** — the operational artifacts required to deploy safely, including pipelines, environment separation, secrets management, and progressive delivery.
- **Operations** — runtime configurations, platform baselines, identity and access posture, and change-management.
- **Monitoring** — telemetry, alerting, and observability required to detect issues quickly during runtime.

Each dimension can be implemented at levels that resemble CMMI: from initial/ad hoc, through managed (repeatable), defined (standardized), measured, and optimized. The threshold for each level is not universal; it must be set for the organization.

## Maturity levels in practice

Organizations benefit most by reading the levels not as a checklist but as a descriptive floor:

- **Ad hoc** — risks are recognized but mitigated case-by-case.
- **Managed** — work is repeatable, with a documented owner per activity.
- **Defined** — work is standardized across teams, with shared policy and shared tooling.
- **Measured** — activity is tracked quantitatively and decisions are evidence-based.
- **Optimizing** — feedback drives systematic improvement at the dimension level.

A team at "managed" maturity can still be improving toward "defined". A team at "measured" maturity can still have weaknesses in detection, response, or design. The model rewards consistent progress; it does not reward reaching a level across all dimensions at once.

## Application workflow

1. Agree on the dimensions in scope; corporate-wide assessments help governance, while service-class assessments help engineering.
2. Score each dimension per service class or per platform, using a consistent rubric maintained by the security team.
3. For each dimension, capture the observable artifacts that justify the level. Linking maturity to evidence makes reassessment objective.
4. For dimensions below the target level, define the minimum set of activities required to lift the level and assign owners.
5. Track maturity over time; the same service class should never be assessed twice at the same level without a justification note.
6. Use assessments as inputs to investment discussions, not as a gate. A service that is mature in some dimensions and weak in others still has valuable context.

## Operations-focused considerations

For operations teams, the most relevant dimensions are Design through Monitoring. Operations-specific application of the OWASP DevSecOps Guideline includes:

- encoding platform baselines as code rather than as documented intentions;
- applying purpose-built identity propagation in pipelines (signed, short-lived, audited);
- reviewing change-management control points for separation of duties and least privilege;
- collecting sufficient telemetry for detection and response;
- retaining evidence at each layer for audit purposes;
- applying threat modelling that includes the deployment and runtime platforms, not only the application;
- maintaining runbooks and their exercise records as evidence of operational preparedness.

## Validation evidence

Retain the dimension-level rubric, per-service assessment results, evidence references per dimension, target trajectories, action plans with owners, and review minutes. Record the period of each assessment and the auditor or assessor's identity. Validation requires that the artifacts cited for each level exist in fact, not only in the assessment document.

## Failure modes

Failure modes include assessing all dimensions together and producing a single averaged score that hides weaknesses, treating levels as a gate for go-live so that lower-maturity services appear compliant by exception, redesigning the rubric each cycle so trends are not comparable, and using the assessment to assign blame rather than to direct investment. The model loses value when assessment outcomes are not used.

## Cross-team signal

DevSecOps maturity is rarely owned by any single team: Security provides policy and verification, Operations provides platform and deployment, Engineering produces the artifact, and Product sets acceptance criteria. The assessment is a useful cross-team signal because it lifts these views to a common vocabulary. When teams disagree on posture, the assessment provides a recorded map of who owns what dimension and where the gaps actually are. Without the model, disagreements stall; with the model, they convert into action items assigned along dimension lines.

## Annual review

A useful operational pattern is an annual DevSecOps review where the assessment is presented to the same cross-team governance body that owns other operating reviews. The review's job is to ratify the current state, approve forward investment, and confirm the next review's scope. The review's notes should be retained with the assessment results to provide an audit trail of decisions made about posture changes. The model then becomes more than a report — it becomes the operating mechanism that connects posture to budget and to program decisions.

## Canonical sources

- OWASP DevSecOps Guideline Project: https://owasp.org/www-project-devsecops-guideline/
- OWASP SAMM (Software Assurance Maturity Model): https://owasp.org/www-project-samm/
- OWASP Application Security Verification Standard (ASVS): https://owasp.org/www-project-application-security-verification-standard/

## Scope note

This article summarizes the application of the OWASP DevSecOps Guideline for operations and platform engineering; assessment values and target levels must be set by each organization based on its portfolio, regulations, and risk appetite.
