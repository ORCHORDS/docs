# BIMI Verified Mark Certificate Lifecycle

A Verified Mark Certificate is the piece of paper that turns a logo file into brand evidence. BIMI lets a domain owner assert, via a DNS TXT record, which logo mailbox providers should display next to authenticated mail from that domain. The VMC is the influential upgrade: a Mark Verifying Authority - a CA operating under a documented certification practice statement - issues a certificate binding the logo's trademark to the organizational domain after validating that the applicant owns the mark. Providers weigh VMC-backed logos differently from bare assertions, so for many brands the certificate is what makes BIMI worth deploying. The lifecycle is longer and more procedural than the DNS record it accompanies, and a lapse at any stage silently degrades display without any DNS error to alert you.

## Scope

This article covers the operational lifecycle of VMCs: trademark eligibility and the evidence the MVA requires, issuance, how the certificate is referenced by the BIMI record, renewal timing, and revocation consequences. It is written for brand and infrastructure owners managing BIMI for one or more sending domains. It does not cover BIMI DNS record syntax, SVG logo authoring constraints, selector-based multi-logo setups, or Common Mark Certificates beyond noting that CMCs relax the trademark requirement and follow the same mechanical lifecycle.

## Workflow or implementation guidance

The lifecycle has six stages. Treat trademark work as the long pole; everything downstream is measured in days.

**1. Establish eligibility.** Confirm the logo is a registered trademark in a jurisdiction the MVAs recognize and that the registration covers the exact visual mark you intend to display. The certificate binds the mark as registered, not as designed - a restyled wordmark diverging from the registration drawing will fail evidence comparison.

**2. Prepare the artifacts.** Produce the logo in the constrained SVG profile BIMI requires, square and small, and obtain the trademark registration certificate or registry extract. Assemble proof of control over the organizational domain and the legal entity holding the mark.

**3. Select an MVA and complete validation.** The BIMI Group publishes the issuer list (DigiCert, GlobalSign, and SSL.com at the time of this writing) with each authority's CPS, certificate transparency log URLs, CRL endpoints, roots, and audit reports. Choose deliberately: providers each decide which MVAs they trust, and presence on the list does not guarantee acceptance. Validation follows CA-industry practice - organization vetting, domain control, trademark evidence comparison - and typically takes days to a few weeks.

**4. Deploy the certificate.** Publish the BIMI DNS record pointing to the logo and the issued certificate, keyed by selector. After DNS propagation, verify with an independent BIMI validator that the record resolves and the referenced artifacts are fetchable.

**5. Operate and monitor.** Track three clocks: certificate expiry, trademark registration maintenance (renewals, ownership changes, challenges), and domain control. A trademark that lapses or transfers undermines the certificate even while the X.509 object remains technically valid.

**6. Renew ahead of expiry.** MVAs issue certificates on roughly annual terms. Begin renewal at least a month before expiry, because renewed certificates may hash differently and require a DNS record update even when the logo has not changed. Run old and new in parallel across the renewal window.

## Controls

- Trademark evidence dossier - registration number, jurisdiction, registry extract, legal-entity alignment - refreshed whenever the registration or corporate structure changes.
- Certificate expiry calendar with 60- and 30-day alerts, sized to absorb MVA validation queues.
- MVA posture verification at selection and annually: CPS, CT log coverage, CRL availability, audit reports.
- Domain-control continuity: stable DNS and registrar contacts throughout the certificate's life.
- Artifact immutability: the SVG the certificate vouches for must stay byte-identical to what DNS serves; any redesign forces re-validation, not re-upload.
- Dual-record overlap during renewal until provider caches turn over.
- Per-provider display monitoring, since acceptance policy differs across mailbox providers.
- Audit trail linking each certificate to the evidence pack that justified it.

## Validation evidence

- A BIMI record validator confirming the record resolves, the logo URL is fetchable, and the certificate reference is intact.
- The issued VMC inspected with standard X.509 tooling: subject organization, logo hash, validity window, issuing MVA.
- Certificate Transparency log entries matched against the MVA's published CT log URL.
- Provider-side confirmation of logo display on participating mailbox providers before and after renewal.
- Trademark registry status extract dated within the certificate's validation window.
- Renewal-window telemetry showing zero display loss during old/new certificate overlap.

## Failure modes and correction

Logos silently disappearing is the dominant failure, usually certificate expiry - renewals starting too late leave a gap while the MVA re-validates. The fix is the 30-to-60-day lead and parallel publication. Display that never appears despite a valid certificate usually means the provider does not honor that MVA or requires stricter evidence; confirm acceptance provider by provider rather than assuming the issuer list transfers. Issuance rejection most often traces to logo-trademark mismatch: align the SVG to the registration drawing or register the variant you actually use. A certificate working for one domain and not another indicates organizational-domain scoping - publish the record where providers look and check subdomain inheritance. Post-acquisition or post-rebrand breakage means the trademark evidence chain broke; reissue under the new entity once the registry reflects the change. CRL or CT infrastructure problems at the MVA can cause providers to distrust batches of certificates; monitor the issuer's status and be prepared to reissue from another authority, which the evidence dossier makes survivable.

## Limitations

VMC issuance is trademark validation, not a security audit; a certified logo says the applicant owns the mark, not that the mail is benign. Provider participation is uneven and each sets its own acceptance bar, so compliance alone cannot guarantee display. The trademark-jurisdiction requirement excludes brands with unregistered marks from VMCs entirely - CMCs exist for that case but carry less weight. Renewal cadence and evidence re-validation impose ongoing cost that scales with brands and domains. The certificate binds one mark to one organization; multi-brand portfolios need one each. BIMI display additionally requires passing DMARC enforcement, so the certificate lifecycle sits atop a separate authentication dependency with its own failure modes.

## Canonical sources

- [BIMI Group: Mark Certificate Issuer Information](https://bimigroup.org/vmc-issuers/)
- [BIMI Group: Implementation Guide](https://bimigroup.org/implementation-guide/)
- [BIMI Group: Supporting Documents](https://bimigroup.org/supporting-documents/)
- [BIMI Group: FAQ](https://bimigroup.org/faq/)
- [M3AAWG best practices and published documents](https://www.m3aawg.org/published-documents/)
