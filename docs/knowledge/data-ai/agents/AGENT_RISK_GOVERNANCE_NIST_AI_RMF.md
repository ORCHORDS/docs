# Agent Risk Governance with the NIST AI Risk Management Framework

## Purpose

Agent deployments create and absorb risk across model behavior, system integration, organizational use, and societal impact. The NIST AI Risk Management Framework (AI RMF 1.0) defines a four-function structure—Govern, Map, Measure, Manage—and supporting profiles such as the Generative AI Profile. AI RMF is voluntary, outcome-oriented, and intended to be used with existing privacy, security, civil rights, and operational risk programs.

AI RMF is not a certification and it does not prescribe a specific architecture. It describes functions, categories, and subcategories that an organization can use as a target for evidence and conversation. Adapting it to agents means making the four functions concrete for runtime controls, lifecycle decisions, and accountability.

## Governance workflow

1. Assign accountability for agent risk. Name roles and decision rights for system owners, operators, reviewers, approvers, incident responders, and end-user support. Document escalation paths and review cadence.
2. Establish an AI risk policy aligned with existing risk and compliance programs. Define acceptable uses, prohibited uses, required reviews, and the relationship to model deployment, third-party services, and data sharing.
3. Maintain an inventory of agent systems, components, datasets, and dependencies. Capture purpose, owner, data classifications, affected populations, tools, model identifiers, deployment revision, and approved expiration.
4. Set competency, training, and access requirements for builders and operators. Restrict production access based on training, background review, and least privilege.
5. Document processes for complaints, feedback, change management, and retirement. Ensure that deprecation retains evidence and supports downstream system continuity.
6. Align with applicable regulation and standards. AI RMF does not satisfy obligations such as data-protection law, accessibility, sector regulation, or procurement; integrate with those programs explicitly.

## Map workflow

1. Describe the deployment context, including intended users, task scope, decision authority, consequences of error, and human oversight points.
2. Characterize each data input and output by category, sensitivity, source, retention, and lawful basis. Note when data is personal, confidential, regulated, third-party, or potentially adversarial.
3. Identify affected stakeholders and assess potential harms. Include errors of commission and omission, bias, privacy impact, safety, economic, autonomy, and environmental effects where relevant.
4. Map applicable laws, standards, contractual commitments, and internal policies. Identify gaps where mitigation, review, or contractual action is required.
5. Document assumptions and trust boundaries, including dependencies on external model providers, retrieval corpora, third-party tools, and operator tooling. State what evidence justifies each trust assumption.

## Measure workflow

1. Select metrics aligned with risk objectives: correctness, reliability, calibration, fairness across relevant groups, refusal accuracy, latency, cost, recovery time, audit-event fidelity, and user-reported harm.
2. Combine internal evaluation, structured user feedback, monitoring, and where appropriate external assessment. Report uncertainty and sample limitations instead of presenting point estimates as universal claims.
3. Track provenance and version of model, data, prompts, and policy alongside each measurement. Use the same artifacts in production to interpret drift.
4. Run targeted red-team and adversarial testing using documented scope. Treat security, safety, and fairness tests as distinct programs with their own acceptance criteria.
5. Conduct pre-deployment and periodic post-deployment reviews. Trigger additional review on material changes to model, instructions, data, tools, or scope.

## Manage workflow

1. Implement prioritized controls, starting with high-impact risks. Where feasible, place enforcement at deterministic boundaries rather than relying on model self-restraint.
2. Define response plans for risks that materialize, including degraded modes, rollback, communication, and learning. Connect these to the organization’s incident response.
3. Manage third-party risk through contractual terms, assessments, monitoring, and exit planning. Do not assume that a vendor’s certification satisfies your risk obligations.
4. Document residual risk and acceptance authorities. Treat risk acceptance as a time-bound decision with conditions and review dates.
5. Maintain continuous improvement: incorporate incidents, audit findings, and measurement results into policy, design, and operational practice.

## Validation and evidence

Govern evidence should include policy, roles, inventory, training records, change-management logs, and review minutes. Map evidence should include system descriptions, data classifications, stakeholder analyses, applicable law register, and trust-boundary diagrams. Measure evidence should include test protocols, environment snapshots, metric calculations with uncertainty, sample data lineage, and red-team reports. Manage evidence should include control mappings, decision records, incident records, third-party assessments, and risk acceptance documents.

Audit sampling and effectiveness. A documented control does not prove effectiveness; observe it in operation. Track metric trends and control exceptions. Cross-reference AI RMF evidence with security, privacy, and compliance evidence so a single action supports multiple programs and contradictions are visible.

## Failure handling

If a control fails, treat the failure as a measurement and governance signal, not just an incident. Update the risk profile, decide whether mitigation or acceptance is appropriate, and revise the next review cycle. Avoid the trap of replacing one estimation-based screening with another if the underlying design issue is deterministic.

If AI RMF adoption conflicts with another requirement, the stricter applicable obligation prevails. Frame conflicts in terms of specific risks and evidence rather than as program-versus-program disputes. Where data is unclear, follow documented assumptions, escalate, and note residual uncertainty rather than presenting a resolved but unsupported conclusion.

## Canonical sources

- NIST, *AI Risk Management Framework 1.0*: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST, *AI RMF Generative AI Profile* (NIST AI 600-1): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- NIST, *AI RMF Playbook*: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook
- NIST, *AI Risk Management Framework Crosswalks*: https://airc.nist.gov/AI_RMF_Knowledge_Base/Crosswalks