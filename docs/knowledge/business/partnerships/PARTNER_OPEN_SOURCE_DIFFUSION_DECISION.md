# Partner Open-Source Diffusion Decision

Joint development creates knowledge that both partners could publish as open source: a library, a protocol implementation, a connector, a specification. Publishing is strategically powerful and strategically irreversible. This article defines the decision process for when jointly developed knowledge ships under an open-source licence — who decides, on what criteria, with what technical prerequisites, and with what exit posture once published.

## Scope

Covers decisions to release jointly developed software, specifications, datasets, or documentation under an open-source licence, unilaterally or through a partner-consent mechanism. In scope: candidate assessment, consent mechanics between partners, licence selection constraints, publication prerequisites, and post-publication governance. Out of scope: inbound licence screening of partner contributions and the internal decision to consume open source, which are separate disciplines. The accountable role is the **diffusion decision owner**, a business owner with authority over the asset, advised by IP and security functions.

## Workflow or implementation guidance

Frame the decision as a diffusion choice, not a disposal. Publishing jointly developed knowledge open source sets its price at zero, multiplies its distribution, invites external contribution, and forecloses exclusive licensing of the published scope forever. The question is whether network effects, standard-setting advantage, ecosystem recruitment, or maintenance relief exceed the foregone licensing value. Write the strategic case down before choosing a licence, because licence choice should follow strategy, not precede it.

Confirm unilateral rights first. Jointly developed material may be jointly owned, licensed between the partners, or held by one with rights granted to the other; the consent required to publish depends on this structure. Joint patent owners in some jurisdictions can license without co-owner consent, joint copyright owners generally cannot exclusively license without consent, and the partnership agreement may impose a consent right regardless of statutory default. Map the ownership position and obtain whatever consent the agreement and applicable law require, in writing, referencing the exact material and licence.

Inventory what would ship. Open-source publication of a component ships everything needed to build and use it: source, tests, build tooling, documentation, and — critically — the dependency tree. The tree decides feasibility more often than the component itself: a strong component depending on a partner's proprietary library cannot ship open source without that dependency's owner consenting or a decoupling refactor. Inventory inbound licences across the tree, including transitive dependencies, and resolve conflicts before announcement.

Apply the value-and-risk screen. On value: does publication grow adoption of something the partners monetise adjacently — a paid platform, a service, a certification? On risk: does the material embody patentable inventions whose publication creates prior art that destroys the partners' own filing options, embed security-sensitive implementation details, or disclose architecture that raises attack surface? Patent counsel should review publication timing against pending applications on the same subject matter.

Select the licence against the strategic case. Permissive licences maximise diffusion and commercial adjacency; weak copyleft protects against proprietary forks of the component itself while permitting use in proprietary products; strong copyleft or network copyleft keeps the published scope and derivatives open but constrains embedding. Confirm both partners' outbound models are compatible with the choice, since the same licence binds both.

Run publication prerequisites: a clean, reproducible build from the published tree; license and notice files in place with third-party attribution assembled; contributor arrangements for future inbound contributions, including a developer certificate of origin process or a contributor licence agreement; security review of the published code; and an export-control screen, since publication of controlled technology online is an export to all destinations.

Establish post-publication governance before release: which partner's organisation hosts the repository and trademark, how maintenance costs are shared, how security disclosures are triaged, and how the project can be archived if the partnership ends. Once published, the licence cannot be revoked for existing copies; governance only shapes the future.

## Controls

- Decision record per candidate: strategic case, ownership position, consents obtained, screen results, licence chosen, approver.
- Consent instrument from each partner referencing exact material, commit hash or version, and licence.
- Dependency tree inventory with inbound licence resolution attached to the decision record.
- Patent-timing review note covering pending applications on the same subject matter.
- Publication checklist: reproducible build, notices and attribution, contribution process, security review, export screen.
- Governance charter naming hosting, trademark, maintenance funding, security triage, and archival path.
- Post-publication review at six and eighteen months comparing observed adoption, contribution, and maintenance load against the strategic case.

## Validation evidence

The decision process produces decision records, consent instruments, dependency inventories, patent-timing notes, completed publication checklists, the governance charter, and post-publication reviews. Validate by selecting a published component and tracing the shipped tree to its decision record: the commit hash on the consent instrument should match what was actually published, and every third-party notice in the release should appear in the attribution inventory. Reverse-test: pick three dependencies in the published tree and confirm each appears in the inventory with its licence. For security review, confirm the review covered the exact published version rather than an earlier branch. Check the governance charter's named owners are current staff and that the security-disclosure channel has been tested at least once. Where a licence was changed between versions of the project, retain the decision record for the change and the version boundary at which it took effect.

## Failure modes and correction

Common failures: publishing to be generous without a strategic case, then withdrawing support when costs land; consent assumed from silence — one partner never objected, so the other shipped, leaving a co-owned work published without authority; dependency trees screen-shallow, so a partner proprietary library ships inside a permissively licensed release; publication of an implementation the same week its patent application was drafted, creating avoidable prior-art disputes; and no governance, so the project's maintainer leaves and security reports rot. Correct consent failures by immediate counsel involvement, pausing distribution where feasible, and negotiating ratification — retroactive consent cures authority, though not always reputational cost. Dependency contamination requires a patched release with the proprietary material removed and the affected versions clearly flagged. For governance decay, either fund maintenance explicitly or archive the repository with a final notice rather than leaving it implicitly supported.

## Limitations

Publication decisions are irreversible as to distributed copies; correction changes the future, not the past. Co-ownership consent requirements vary by jurisdiction and right type, so the consent map here is procedural. Strategic value of diffusion is estimable but not measurable in advance; post-publication reviews are judgments. Export-control screening of published technical content requires expert judgment on controlled parameters. This is decision-process guidance, not legal or strategic advice for a specific asset.

## Canonical sources

- Open Source Initiative — Licenses and terminology: https://opensource.org/licenses
- SPDX — License list and identifiers: https://spdx.org/licenses/
- GitHub Docs — Open source guidance: https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions
- WIPO — Technology licensing resources: https://www.wipo.int/patents/en/
