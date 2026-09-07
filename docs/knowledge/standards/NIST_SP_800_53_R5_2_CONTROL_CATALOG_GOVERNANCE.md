# NIST SP 800-53 Revision 5.2 Control Catalog Governance

## 1. Scope
This card defines governance for the application, tailoring, assessment, and continuous review of the NIST SP 800-53 Revision 5.2 control catalog within the organization's information security program. It applies to all systems that process, store, or transmit organizational data and to all personnel responsible for control implementation, assessment, authorization, and monitoring. The card establishes authoritative sources, structural conventions, baseline selection rules, overlay application, assessment linkage, automation expectations, and review cadence.

## 2. Normative references
- NIST SP 800-53 Revision 5.2, Security and Privacy Controls for Information Systems and Organizations
- NIST SP 800-53B, Control Baselines for Information Systems and Organizations
- NIST SP 800-53A Revision 5, Assessing Security and Privacy Controls
- NIST SP 800-37 Revision 2, Risk Management Framework for Information Systems and Organizations
- NIST SP 800-30 Revision 1, Guide for Conducting Risk Assessments
- NIST SP 800-60 Volumes I and II, Guide for Mapping Types of Information and Information Systems to Security Categories
- NIST SP 800-137, Information Security Continuous Monitoring for Federal Information Systems and Organizations
- FIPS 199, Standards for Security Categorization of Federal Information and Information Systems
- FIPS 200, Minimum Security Requirements for Federal Information and Information Systems
- ISO/IEC 27001:2022, Information Security Management Systems
- FedRAMP Baseline documents

## 3. Terms and definitions
Control: a safeguard or countermeasure prescribed for an information system to protect the confidentiality, integrity, and availability of the system and its information.
Enhancement: a statement of security capability added to a control or control statement that provides additional specificity or rigor.
Baseline: a set of controls selected to address the protection needs of a particular impact level.
Overlay: a set of controls derived from the application of tailoring guidance to a defined community, technology, or threat scenario.
Tailoring: the process by which control baselines are modified to align with the organization's mission, environment, or constraints.
Assessment: the testing and evaluation of control implementations against prescribed criteria.
Continuous monitoring: the maintenance of ongoing awareness of information security, vulnerabilities, and threats.

## 4. Background
NIST SP 800-53 originated as a companion to FIPS 200 and has matured through five revisions. Revision 5 consolidated privacy controls alongside security controls, introduced supply chain risk considerations, and aligned with the Risk Management Framework. Revision 5.2 incorporates editorial refinements, additional control enhancements, and clarified control statement syntax. The catalog serves as the authoritative reference for federal agencies, contractors, and aligned private-sector programs, including FedRAMP. Cross-references within this document are expressed in `NIST_SP_800_53_R5_2_CONTROL_CATALOG_GOVERNANCE.md:5` form.

## 5. Control families (AC, AT, AU, CA, CM, CP, IA, IR, MA, MP, PE, PL, PM, PS, PT, RA, SA, SC, SI, SR)
AC — Access Control: account management, separation of duties, least privilege, session lock, and wireless access restrictions.
AT — Awareness and Training: security awareness, role-based training, and practical exercise obligations.
AU — Audit and Accountability: auditable event selection, audit record generation, protection, review, and retention.
CA — Assessment, Authorization, and Monitoring: control assessments, system interconnections, plan of action and milestones, and continuous monitoring strategy.
CM — Configuration Management: baseline configuration, change control, configuration settings, and least functionality.
CP — Contingency Planning: contingency plan development, training, testing, backup, and system recovery.
IA — Identification and Authentication: identifier management, authenticator management, biometric usage, and device identification.
IR — Incident Response: incident handling, monitoring, reporting, testing, and response coordination.
MA — Maintenance: maintenance policy, controlled maintenance, and maintenance tools.
MP — Media Protection: media access, marking, storage, transport, sanitization, and use restrictions.
PE — Physical and Environmental Protection: physical access authorization, monitoring, visitor control, emergency power, fire protection, and environmental controls.
PL — Planning: system security plan development, rules of behavior, and security architecture documentation.
PM — Program Management: information security program plan, senior leadership oversight, risk management strategy, and workforce management.
PS — Personnel Security: position categorization, screening, termination, transfer, and access agreement management.
PT — PII Processing and Transparency: PII inventory, privacy notices, consent, data quality, and disposal.
RA — Risk Assessment: security categorization, threat and vulnerability identification, and risk response.
SA — System and Services Acquisition: allocation of resources, system development life cycle, external services, and documentation.
SC — System and Communications Protection: boundary protection, transmission confidentiality and integrity, cryptographic key management, and collaborative computing restrictions.
SI — System and Information Integrity: flaw remediation, malicious code protection, monitoring, and spam protection.
SR — Supply Chain Risk Management: supply chain controls, supplier assessments, and component authenticity.

## 6. Control structure: control text / discussion / enhancements
Each control contains a control statement that establishes the safeguarding expectation, a supplemental discussion section that provides explanatory context and implementation guidance, and zero or more enhancements that strengthen or extend the baseline control. Control identifiers use the format "##-##" where the first field is the family identifier and the second is the sequential number. Enhancements append a parenthetical sequential number, for example AC-2(1). Control text is normative; discussion is informative.

## 7. Baselines: Low, Moderate, High tailored to system impact
Three impact-derived baselines are defined in NIST SP 800-53B: Low, Moderate, and High. The applicable baseline is determined from the system's security categorization per FIPS 199 across confidentiality, integrity, and availability. The Low baseline applies when all three objectives are low. The Moderate baseline applies when at least one objective is moderate and none are high. The High baseline applies when any objective is high. The selected baseline represents the minimum control set; organizations may select additional controls through tailoring.

## 8. Overlay development and tailoring guidance
Tailoring modifies baseline controls to align with operational environment, mission requirements, technology constraints, and risk determinations. Tailoring actions include scoping, selection, parameterization, supplementation, and compensation. Overlays consolidate tailoring decisions for a defined community, sector, technology, or threat class and may be applied in addition to the baseline. Examples include FedRAMP overlays and the DoD Cloud Computing overlay. Overlays must be documented, reviewed, and approved prior to application.

## 9. Assessment procedure linkage to SP 800-53A
Assessment procedures defined in SP 800-53A are mapped one-to-one with control statements and enhancements. Each procedure contains assessment objectives, determination statements, and potential assessment methods including examine, interview, and test. Assessors shall execute the procedures corresponding to the controls in the authorized baseline, record findings in standardized formats, and feed results into continuous monitoring activities.

## 10. Automation via OSCAL (Open Security Controls Assessment Language)
OSCAL provides machine-readable representations of the catalog and supporting artifacts. The Catalog component represents the control catalog content. The Profile component captures baseline selections, tailoring decisions, and overlay applications. The Component Definition describes reusable implementation patterns. The System Security Plan expresses how the system implements controls. The Assessment Plan documents assessment scope, methods, and schedule. The Assessment Results record findings and determinations. The Plan of Action and Milestones tracks remediation items. Organizations shall publish and consume these artifacts in OSCAL formats to enable automated assessment, validation, and continuous authorization workflows.

## 11. Compliance evidence (SOC 2, FedRAMP, RMF, ISO 27001 mappings)
Control mappings support evidence collection across multiple frameworks. SOC 2 Trust Services Criteria map to AC, AU, CA, CM, and SC families. FedRAMP baselines reference SP 800-53 directly. The Risk Management Framework in SP 800-37 sequences control selection, implementation, assessment, authorization, and monitoring. ISO/IEC 27001 Annex A controls map to SP 800-53 controls with cross-references maintained in NIST SP 800-53 Appendix I.

## 12. Risk register
Risks identified through control assessment shall be entered into the organizational risk register with unique identifiers, descriptions, likelihood and impact ratings, risk responses, owners, and target closure dates. Risk register entries shall be linked to associated controls, assessment findings, and POA&M items.

## 13. Review cadence
This card is reviewed on a 180-day cycle by the responsible governance authority. Review inputs include OSCAL profile diff reports, assessment finding trends, regulatory changes, and supply chain risk events. Material changes trigger a full revision; editorial changes trigger a minor revision with changelog entries.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.