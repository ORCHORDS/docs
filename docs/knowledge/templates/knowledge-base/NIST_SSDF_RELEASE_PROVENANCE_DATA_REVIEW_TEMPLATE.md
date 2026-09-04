# NIST SSDF Release Provenance Data Review Template

Use this evidence record to operationalize NIST SSDF v1.1 task PS.3.2 on collecting and sharing provenance data for components of software releases. The organization should define the exact provenance format, audience, retention, and disclosure model appropriate to its products and risk.

## Review metadata

- Product/release: `<name/version>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Release artifact reference: `<reference>`
- Provenance/SBOM format or mechanism: `<format/mechanism>`

## Release-component coverage

| Component/artifact class | Included in provenance record? | Version/identity captured? | Source/origin captured? | Integrity protected? | Consumer/response access defined? | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `<component>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] The release has an identifiable provenance/component record covering the material components required by organizational policy.
- [ ] Provenance data is regenerated or updated when release components change.
- [ ] Provenance records are associated with the specific software release or artifact they describe.
- [ ] The integrity of provenance data is protected according to the organization’s release-evidence model.
- [ ] Operations, vulnerability-response, or other internal teams that need provenance data can obtain it through a defined process.
- [ ] External sharing with acquirers/customers, when applicable, follows a defined disclosure policy and supported format.
- [ ] Provenance retention is sufficient to support vulnerability investigation for supported releases.
- [ ] Missing or unknown component provenance is treated as an evidence gap rather than silently recorded as complete.
- [ ] The organization can reconcile the provenance record with resolved dependencies/build inputs for a representative release.

## Verification exercise

- Selected release: `<reference>`
- Resolved/build component source: `<reference>`
- Provenance record: `<reference>`
- Reconciliation result: `<result>`
- Integrity verification result: `<result>`
- Internal retrieval/share test: `<result>`
- External/acquirer delivery test if applicable: `<result or n-a>`

## Findings and actions

- Coverage gaps: `<text>`
- Stale provenance: `<text>`
- Integrity/access gaps: `<text>`
- Corrective actions/owner/date: `<text>`

## Sources

- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — v1.1 addition PS.3.2: https://csrc.nist.gov/projects/ssdf
