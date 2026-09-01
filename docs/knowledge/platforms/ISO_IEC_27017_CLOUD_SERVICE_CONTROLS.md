# ISO/IEC 27017 Cloud Service Controls

## Purpose

ISO/IEC 27017:2015 is the cloud-sector code of practice that supplements ISO/IEC 27002 with cloud-specific information security controls and implementation guidance. It is the authoritative cloud-sector baseline for both cloud service customers and cloud service providers, and is one of the standards most commonly invoked in cloud procurement, audit, and shared-responsibility documentation.

## Scope

The publication addresses controls for both provider and customer roles, additional cloud-sector implementation guidance, and a set of cloud-specific control objectives. It does not, by itself, provide a certification program; conformity is typically demonstrated through ISO/IEC 27001 certification plus a statement of applicability that references 27017.

## How 27017 relates to 27001 and 27002

ISO/IEC 27001 defines an information security management system (ISMS). ISO/IEC 27002 catalogs information security controls. ISO/IEC 27017 adds cloud-sector implementation guidance and additional controls that an organization can choose to apply. In practice, a 27017-aligned ISMS reuses the 27002 controls and adds the 27017 controls where the cloud context requires them.

## Control structure

The 27017 controls are organized under the same clauses as 27002. For each control, the publication provides:

- a cloud-sector implementation guidance note for the cloud service customer;
- a cloud-sector implementation guidance note for the cloud service provider; and
- additional cloud-specific controls not present in 27002.

The dual guidance is the most operationally useful part of the publication: it tells the customer what to ask for and tells the provider what to publish.

## Selected cloud-sector controls

The publication adds cloud-specific controls in several areas. Examples include:

- **Shared roles and responsibilities**: documenting which party implements which control, with a shared-responsibility matrix that is reviewed on change.
- **Removal of cloud service customer assets**: handling of customer data on contract termination, including data return, deletion, and storage of deletion evidence.
- **Segregation in virtualized environments**: hardening of the virtualization layer and segregation between tenants at the hypervisor and management plane.
- **Virtual machine hardening**: baseline configuration, image provenance, and patch discipline.
- **Administrator operation of cloud infrastructure**: privileged-access discipline, logging, and break-glass procedures.
- **Monitoring of cloud services**: agreed metric set and review cadence.

## Engineering workflow

1. Identify cloud services in scope and the role the organization plays for each (customer, provider, both).
2. Build a control matrix that lists the 27002 baseline and the 27017-specific controls with role assignment.
3. For each customer role, request the provider's 27017-aligned statement of applicability or equivalent artifact and store it.
4. For each provider role, publish the implementation guidance for customers to consume.
5. Attach implementation evidence to each control row, naming the artifact path or URL.
6. Review the matrix when contracts are renewed, when services change, or when a significant incident occurs.

## Controls and evidence

- Statement of applicability (SoA) with both 27002 and 27017 controls.
- Provider's 27017-aligned SoA or equivalent artifact, scoped to the SKUs in use.
- Shared-responsibility matrix with named owners and dated contract references.
- Configuration exports, audit logs, and incident records that back each control row.
- Termination playbook with evidence of data return or deletion.

## Validation

- Internal audit samples at least 10% of control rows and verifies the evidence artifact exists and is in scope.
- Provider attestations are checked for scope (SKU, region, impact level) and for currency.
- The shared-responsibility matrix is reviewed jointly with the provider at least annually.
- Termination playbook is exercised in a tabletop or a real offboarding.

## Failure modes and corrections

- Treating the SoA as exhaustive — correct by reviewing the controls actually deployed in the environment, not just the ones listed.
- Assuming provider 27017 alignment means all controls are inherited — correct by reading the SoA scope and the SKUs in use.
- Documenting shared-responsibility only in the contract without operationalizing it — correct by attaching the matrix to the runbook and the change process.
- Treating 27017 as a separate ISMS — correct by integrating 27017 into the existing 27001 ISMS, not as a parallel program.

## Limitations

- The publication is a code of practice, not a certification. ISO/IEC 27017 statements of conformity typically rely on 27001 certification plus an extended SoA.
- The cloud-sector controls cannot anticipate every provider-specific feature; the matrix must still be customized.
- It does not, by itself, address regulatory obligations such as PCI DSS, HIPAA, or GDPR.
- It does not prescribe control automation or evidence-collection tooling.

## Canonical sources

- ISO/IEC 27017:2015 (ISO, primary authority) — Code of practice for information security controls based on ISO/IEC 27002 for cloud services: https://www.iso.org/standard/43757.html
- ISO/IEC 27002:2022 (ISO, primary authority) — Information security, cybersecurity and privacy protection — Information security controls: https://www.iso.org/standard/27002

## Scope note

This article summarizes project-neutral use of ISO/IEC 27017 alongside ISO/IEC 27001 and ISO/IEC 27002. It does not claim that any specific ISMS is certified or that any specific system is compliant.