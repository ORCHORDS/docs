# AI Risk Tiering Practice Governance

## 1. Scope
This standard defines how teams classify AI and machine learning
models into risk tiers so that proportional controls can be applied
across the model lifecycle, from development through deployment and
retirement.

It applies to all AI/ML models developed, procured, or operated by
or on behalf of the platform, including traditional machine
learning, deep learning, and generative AI systems. It does not
override model-specific risk assessments documented in service
runbooks.

## 2. Normative references
The following documents are referenced and inform the requirements
of this standard:

- ISO/IEC 42001:2023 Artificial Intelligence Management System (AIMS).
- ISO/IEC 23894:2023 Artificial Intelligence — Guidance on Risk
  Management.
- NIST AI Risk Management Framework (AI RMF 1.0 and subsequent
  updates).
- EU AI Act (Regulation (EU) 2024/1689).
- Platform AI Model Lifecycle Playbook.

## 3. Terms and definitions
For the purposes of this standard, the following terms apply:

- **AI risk tier**: a classification reflecting the severity and
  likelihood of harm associated with an AI system's deployment.
- **Prohibited use**: a use case that the platform will not
  implement due to unacceptable risk.
- **High-risk system**: a system whose failure or misuse could
  materially affect safety, fundamental rights, or critical
  operations.
- **Model card**: a documented artefact describing intended use,
  limitations, evaluation results, and operational characteristics.

## 4. Risk tier definitions
AI systems MUST be classified into at least four tiers: `prohibited`,
`high`, `limited`, and `minimal`. Tier assignment MUST be documented
in the model card and approved by the AI governance reviewer before
development proceeds beyond experimentation.

## 5. Tier-specific controls
Each tier MUST define proportionate controls covering data
governance, evaluation, observability, access, and incident response.
High-risk systems MUST additionally define pre-deployment review,
ongoing monitoring, and rollback procedures documented in the model
lifecycle playbook.

## 6. Reassessment triggers
Risk tier MUST be reassessed when any of the following occur: change
in training data distribution, change in deployment context,
discovery of a new vulnerability class, or material change in
upstream regulatory guidance.

## 7. Prohibited uses
The platform MUST maintain a published list of prohibited uses
informed by applicable regulation and platform ethics guidance. New
prohibited uses MUST be reviewed by the AI governance body before
adoption.

## 8. Roles and responsibilities
The model owner is accountable for the risk tier and supporting
documentation. The AI governance body owns tier definitions and the
prohibited-uses list. The platform security team owns alignment with
applicable regulation.

## 9. Exception handling
Any exception to tier-specific controls MUST be approved by the AI
governance body and recorded in the AI exception register with
mitigation owners and review date.

## 10. Audit and evidence
Model cards, tier assessments, and exception records MUST be
retained for at least 24 months in the AI governance archive.

## 11. Reporting
Risk tier distribution and exception volume MUST be reported to
executive stakeholders at least quarterly.

## 12. Change management
Material changes to tier definitions or the prohibited-uses list
MUST follow the platform change management procedure and be
communicated to dependent teams before rollout.

## 13. Review cycle
This standard is reviewed at least annually or when material changes
occur in upstream AI regulation, risk frameworks, or platform
practice.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
