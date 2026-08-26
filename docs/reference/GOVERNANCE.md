# Repository Governance

This file describes how the **ORCHORDS/docs** repository itself is governed:
who maintains it, how changes are accepted, and how disagreements are
resolved. For ORCHORDS company governance policy, see
[Policy Hierarchy](../policies/governance/POLICY_HIERARCHY.md) and
[Corporate Governance](../policies/governance/GOVERNANCE.md).

## Maintainers

The repository is maintained by [ORCHORDS](https://github.com/ORCHORDS).
CODEOWNERS records ownership per documentation category; all categories are
currently owned by the maintaining account.

## How changes are accepted

- **Routine maintenance** (corrections, freshness updates, new documents
  within an existing category) is committed directly to `main` by authorized
  maintainers under the checklist in [CONTRIBUTING.md](../../CONTRIBUTING.md).
- **External contributions and larger changes** arrive as pull requests.
  A maintainer reviews them against the same checklist before merge. The
  documentation-quality workflow must pass.
- Every change must respect the public-repository boundary in
  [README.md](../../README.md) (no credentials, topology, customer data, or
  unannounced work).

## How corrections and disputes are resolved

1. A factual or standards claim is challenged through a documentation issue
   with a primary public source, when available.
2. The maintainer either applies the correction or explains the reasoning in
   the issue.
3. Standards status follows
   [Framework Status Policy](../policies/standards/FRAMEWORK_STATUS_POLICY.md):
   drafts are labeled drafts, superseded editions are marked superseded, and
   nothing is presented as a requirement before it is one.
4. Terminology follows
   [Public Assurance Terminology](../policies/standards/PUBLIC_ASSURANCE_TERMINOLOGY.md):
   "certified", "compliant", "audited", and "implemented" are only used with
   evidence backing.

## Document control

Controlled documents carry YAML front matter (`status`, `last-reviewed`,
`next-review`, `review-cycle`) defined in
[Document Control](../policies/governance/DOCUMENT_CONTROL.md), and
`.github/scripts/check_docs.py` enforces it on every change.
