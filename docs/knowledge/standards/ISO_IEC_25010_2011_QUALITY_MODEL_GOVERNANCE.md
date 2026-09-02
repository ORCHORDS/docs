# ISO/IEC 25010:2011 Systems and Software Quality Model Governance

## Purpose

ISO/IEC 25010:2011 defines a quality model for systems and software products. The model comprises eight quality characteristics: functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, and portability. Governance ensures that quality requirements are expressed in terms of these characteristics, that quality is measured consistently across projects, and that quality targets align with stakeholder needs.

## Current context and source status

ISO/IEC 25010:2011 was published as the first edition, replacing ISO/IEC 9126-1:2001. The standard defines a quality model but not specific metrics; metrics are addressed in ISO/IEC 25023. The model is widely used for quality requirements and for testing strategies. Verify the current edition before treating any sub-characteristic identifier as a current requirement.

## Governance workflow and controls

### 1. Express quality requirements using the model

Express quality requirements in terms of the eight characteristics and their sub-characteristics. For example, a security requirement is expressed under the security characteristic with sub-characteristics (confidentiality, integrity, non-repudiation, authenticity, accountability).

### 2. Define measurable quality targets

For each quality requirement, define a measurable target. Use ISO/IEC 25023 metrics where applicable. Document the measurement procedure, the target value, and the sampling strategy.

### 3. Establish quality gates

Define quality gates at key project milestones. For example, at code complete, verify maintainability metrics. At release candidate, verify performance efficiency and security metrics.

### 4. Integrate with testing

Map quality characteristics to testing activities. Functional suitability is verified through functional testing. Performance efficiency through performance testing. Compatibility through interoperability testing. Usability through user testing. Reliability through reliability testing.

### 5. Track quality over time

Track quality metrics across releases. Trend quality improvement or regression. Report quality to the governing body.

### 6. Review and update

Review the quality model application when the product changes significantly or when the underlying ISO/IEC 25010 standard is updated.

## Validation and evidence

- Quality requirements specification per system.
- Measurement procedures with targets.
- Quality gate records.
- Test plans mapped to quality characteristics.
- Trend reports on quality metrics.

## Failure correction

Common defects include unmeasured quality characteristics, quality gates that are not enforced, and quality metrics that are not actionable. Corrective actions include a quality coverage matrix, mandatory quality gate sign-off, and a metric utility review.

## Limitations

- ISO/IEC 25010 defines a model, not specific metrics.
- Some characteristics (for example, usability) are difficult to measure objectively.
- The model is product-focused; it does not directly cover process quality (use ISO/IEC 33000 for process quality).
- The standard is not a certifiable management system standard.

## Canonical sources

- ISO/IEC 25010:2011, Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — System and software quality models, first edition.
- ISO/IEC 25023, Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Measurement of system and software product quality.
- ISO/IEC 33000 family, process quality standards.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for testing strategy, the security leaf for security quality, and the operations leaf for reliability metrics.
