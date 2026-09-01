# ISO/IEC 27018 PII in Public Cloud

## Purpose

ISO/IEC 27018:2019 is the code of practice for protection of personally identifiable information (PII) in public cloud services acting as PII processors. It is the authoritative baseline that public-cloud customers and providers cite when they need to demonstrate that the provider's handling of customer PII meets an internationally recognized PII-protection standard. The publication is most often invoked in statements of applicability, contractual exhibits, and regulator-facing documentation.

## Scope

The publication addresses public-cloud PII processors and their customer-PII-controller customers. It does not address private clouds, community clouds, or hybrid clouds as first-class citizens, and it does not replace jurisdictional privacy law (such as the EU GDPR or U.S. sectoral privacy law). It provides a baseline that must be combined with applicable law.

## How 27018 relates to 27001 and 27002

ISO/IEC 27018 builds on the ISO/IEC 27001 ISMS structure and the ISO/IEC 27002 control catalog, then adds PII-specific controls and implementation guidance applicable to public-cloud PII processors. A 27018-aligned posture typically means a 27001-certified ISMS whose statement of applicability includes the 27018 controls.

## PII processor obligations

The publication codifies obligations that customers should expect from a public-cloud PII processor. They include:

- processing PII only on the customer's documented instructions;
- returning, transferring, or deleting PII at the customer's choice on contract end;
- helping the customer comply with data-subject rights such as access, correction, and deletion;
- disclosing subprocessor changes to the customer and giving the customer a chance to object;
- ensuring that personnel authorized to handle PII are bound by confidentiality;
- notifying the customer of any unauthorized PII disclosure in a documented timeline;
- supporting the customer's records of processing activities; and
- publishing or otherwise making available the disclosures required by the publication's Annex A controls.

## PII controller-side considerations

The customer remains the PII controller for customer-supplied data. The customer's responsibilities include:

- choosing a service whose contractual and technical controls fit the sensitivity of the data;
- documenting the lawful basis and purpose of processing;
- defining the categories of data and the data-subject population;
- managing identity, access, and retention within the customer's tenant; and
- operating a process for handling data-subject requests that the customer cannot delegate.

## Engineering workflow

1. Identify the data flows that include PII and the public-cloud services that process them.
2. Confirm that the chosen providers are aligned to ISO/IEC 27018 and that the alignment covers the SKUs and regions in scope.
3. For each PII flow, record the data-category, the lawful basis, the retention, and the deletion mechanism.
4. Review the contract for the processor obligations listed above; escalate any gap before signing.
5. Operate the customer's controller-side controls (identity, access, retention, data-subject rights) within the customer's tenant.
6. Re-evaluate after a new PII flow, a regional change, a subprocessor change, or a privacy incident.

## Controls and evidence

- Provider's 27018-aligned statement of applicability, scoped to the SKUs and regions in use.
- Contractual addenda that map to the processor obligations above.
- Customer-side records of processing activities that name the provider and the data categories.
- Subprocessor change log with objection window evidence.
- Deletion evidence for any PII that has been removed from the provider at the customer's request.

## Validation

- Internal privacy and legal review of the contract clauses before signature.
- Periodic review of the provider's SoA scope and currency.
- Sample audit of deletion evidence on a recurring basis.
- A tabletop exercise of the data-subject rights process at least annually.

## Failure modes and corrections

- Treating 27018 alignment as a substitute for jurisdictional privacy law — correct by combining the standard with applicable law and not relying on either alone.
- Accepting the provider's SoA without checking scope — correct by mapping the SKUs and regions in the SoA to the SKUs and regions actually used.
- Allowing subprocessor changes without an objection window — correct by enforcing the contractual right to object and by maintaining a substitute provider plan.
- Delegating data-subject rights entirely to the provider — correct by maintaining a customer-side process for issues that require the controller's authority.

## Limitations

- The publication applies to public clouds; private and hybrid deployments need a different baseline.
- It is a code of practice, not a law; conformance does not satisfy every privacy regulator's requirements.
- It does not prescribe specific technical implementations such as tokenization or format-preserving encryption.
- It does not, by itself, address cross-border transfer mechanisms; the customer must layer those on top.

## Canonical sources

- ISO/IEC 27018:2019 (ISO, primary authority) — Code of practice for protection of personally identifiable information in public clouds acting as PII processors: https://www.iso.org/standard/76559.html
- ISO/IEC 27701:2019 (ISO, primary authority) — Extension to ISO/IEC 27001 and ISO/IEC 27002 for privacy information management: https://www.iso.org/standard/71670.html

## Scope note

This article summarizes project-neutral use of ISO/IEC 27018 for PII in public clouds. It does not provide legal advice and does not certify any specific service as 27018-aligned beyond the scope stated in the source.