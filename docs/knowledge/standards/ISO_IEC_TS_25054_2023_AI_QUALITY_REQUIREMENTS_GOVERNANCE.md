# ISO/IEC TS 25054:2023 AI Quality Requirements Governance

## Purpose

ISO/IEC TS 25054:2023 ("Quality requirements for AI-based systems") defines the structure and content of quality requirements for AI-based systems, extending ISO/IEC 25010 to machine learning and statistical models. Governance ensures ORCHORDS AI-based systems document a structured quality-requirements set, link each requirement to measurable acceptance criteria, and re-evaluate those requirements through the AI lifecycle.

## Current context and source status

ISO/IEC TS 25054 was published in 2023 and is a Technical Specification, not a full International Standard. It is the canonical reference for structuring AI quality requirements and complements ISO/IEC 42001 (AI management system), ISO/IEC 23894 (AI risk management), and ISO/IEC TR 24027 (bias in AI systems). Treat the TS as normative guidance pending its promotion to a full standard; verify the current revision status before adopting.

## Governance workflow and controls

### 1. Scope and stakeholder identification

- For each AI-based system, record the intended use, the foreseeable misuse, the affected population, and the regulatory context.
- Identify stakeholders (data subjects, operators, regulators, end users) and capture their quality expectations.

### 2. Quality model selection

- Use ISO/IEC 25010 quality model as the base; extend with AI-specific characteristics from ISO/IEC TS 25054.
- Document the eight primary quality characteristics and any project-specific sub-characteristics.

### 3. Quality requirement specification

- For each quality characteristic, define at least one measurable requirement using the structure: quality characteristic → property → metric → acceptance criterion.
- Address data quality (representativeness, completeness, timeliness, accuracy), model quality (robustness, fairness, explainability, transparency), and operational quality (latency, availability, observability, retrainability).
- Record the evidence required to demonstrate compliance with each requirement.

### 4. Verification and validation

- For each requirement, document the verification approach (analysis, inspection, test, demonstration) and the test data profile.
- Validate that the system meets the requirement under realistic operating conditions, including degraded inputs and adversarial conditions.

### 5. Lifecycle and change management

- Re-evaluate the quality-requirements set on every material change to data, model, or operating context.
- Capture model lineage and dataset version alongside the requirements so the verification is reproducible.

### 6. Risk and accountability

- Map each requirement to a risk in the AI risk register; record residual risk and acceptance.
- Maintain an audit trail that traces requirements to design decisions, to test results, and to production telemetry.

## Validation and evidence

- Capture a current quality-requirements specification for each production AI-based system.
- Capture verification evidence (test reports, metric results, fairness assessments) per acceptance criterion.
- Capture change records for any requirement update and the rationale.
- Capture the most recent risk register and accountability matrix for each AI-based system.

References: ISO/IEC TS 25054:2023; ISO/IEC 25010:2011; ISO/IEC 42001:2023; ISO/IEC 23894:2023; ISO/IEC TR 24027:2021.
