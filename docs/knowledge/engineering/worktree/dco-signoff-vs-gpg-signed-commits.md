# DCO Signoff vs GPG Signed Commits

## Scope

This article covers the difference between Developer Certificate of Origin sign-off and GPG (or SSH) commit signing, what question each answers, when a project needs one or both, how to enable each in tooling and CI, and the operational costs teams underestimate. It applies to open-source projects, regulated internal repositories, and supply-chain governance programs. It does not cover full SLSA provenance attestations, artifact signing, or tag signing for release pipelines.

## Workflow or implementation guidance

The two mechanisms answer different questions, and conflating them is the most common governance mistake in this area.

**DCO sign-off answers: does the contributor attest they have the right to submit this code under the project's license?** A sign-off is a trailer appended to the commit message: `Signed-off-by: Jane Doe <jane@example.com>`. By adding it, the contributor asserts the Developer Certificate of Origin — that the contribution is theirs or properly licensed for submission. DCO is a legal- provenance statement, costs nothing to produce, and carries no cryptographic strength. Anyone can type the trailer. Its enforcement value comes from the record it creates and the attestation the contributor makes, not from unforgeability.

**GPG (or SSH) signing answers: was this commit actually created by the holder of this private key?** The signature covers the commit's contents and metadata, and verification requires the public key. Signing is an identity-integrity statement with cryptographic strength, and it costs real operational effort: key generation, key storage, key rotation, and verification in CI.

Choose by threat model. If the risk is license provenance — contributions from unknown parties, corporate counsel wants a record — DCO is the fit, and it is why the Linux kernel and most large open-source projects use it. If the risk is impersonation or tampering — a maintainer account is phished, a supply-chain attacker needs to forge authorship — signing is the fit. High-assurance supply-chain programs increasingly require both: DCO for the legal statement, signatures for the identity statement, and CI verifying each.

**Enabling DCO.** Configure it at the client so it is automatic rather than remembered: `git config --global alias.s 'commit -s'` at minimum, or set `git config format.signOff true` for workflows that append it by default. On the hosting side, enable the DCO check so PRs missing sign-off fail status. The friction point is bot- and web-UI-created commits, which do not sign off — the policy must state whether those are exempt or must be recreated locally. For backports, `git cherry-pick -x -s` preserves provenance and adds your sign-off to work you did not author, which is precisely the attestation DCO wants: you assert you have the right to submit this code even though you did not write it.

**Enabling signing.** Generate a dedicated subkey for signing rather than signing with your primary key, set an expiry, and store the key in a hardware token or platform keychain. Configure per-repo or global: `git config --global commit.gpgsign true` and `git config --global user.signingkey <key-id>`. Push the public key to the hosting platform so commits render as verified. The verification half is what most teams skip: enable CI verification so that unsigned or badly signed commits fail the build, because a signature nobody checks is a badge, not a control.

**The escalation ladder for lost keys.** This is where signing programs die. Document, before enforcement, the answer to: a contributor loses their laptop — what happens? The answer is key rotation with a recorded transition, and previously signed history remains valid because verification is per-commit. What must never happen is contributors "solving" key problems by disabling signing, which turns enforcement into a badge program within a quarter.

**When both are on.** A signed commit can lack sign-off; a signed-off commit can lack a signature. CI checks both independently, and the PR status shows two results. Teams that report "commits verified" as a single boolean when only one mechanism is enforced are reporting a number that means less than it appears to.

One more distinction that matters in audits: signing verifies the committer, DCO attests on behalf of the author. When those are different people — a maintainer merging a contributor's patch — sign-off is added by the contributor, and the maintainer may add their own sign-off as the submitter. Two `Signed-off-by` trailers in one commit is normal and correct under DCO semantics.

## Controls

- DCO: sign-off trailer appended by configuration, not memory; hosting-side DCO status check required on PRs; explicit exemption list for bot commits.
- Backports and cherry-picks use `-s` to add the submitter's sign-off alongside provenance from `-x`.
- Signing: dedicated signing subkey with expiry, stored in hardware or keychain; public key registered with the host.
- CI verifies signatures cryptographically and fails unsigned commits — enforcement, not display.
- Documented key-loss rotation procedure, published before signing enforcement begins.
- When both mechanisms are enforced, they are reported as two separate checks, never merged into one boolean.

## Validation evidence

Verification must exercise both the creation and the checking halves of each mechanism:

- Create a commit without sign-off and confirm the DCO check fails the PR; add the trailer via `git commit --amend -s` and confirm it passes.
- Create a signed commit, tamper with its message via a filter, and confirm CI verification fails — this proves verification is real, not cosmetic.
- Confirm the hosting platform renders the commit as verified and that the verified badge's key identity matches the committer, not an unrelated key.
- For cherry-picked backports, confirm the release-branch commit carries both the provenance line and the submitter sign-off.
- Quarterly, compute the share of merges to the default branch with both checks passing, and reconcile against the exemption list — a growing gap between "merged" and "both checks green" means enforcement is being bypassed somewhere.
- Test the key-rotation procedure end to end once a year in a scratch repository, including history remaining verifiable after rotation.

## Failure modes and correction

- **Trailer theater.** Sign-off is typed by rote and nobody reads what they attest. Correction: onboarding covers the DCO's meaning; the check page links the certificate text.
- **Badge without verification.** Signatures display on the host but CI never cryptographically checks them. Correction: add the verification step; unsigned commits fail regardless of what the UI shows.
- **Key-loss death spiral.** One lost key leads to signing disabled "temporarily," then permanently. Correction: the rotation procedure exists before enforcement; disabling signing is a governance decision, not a laptop-recovery step.
- **Web-UI commits.** Fixes made in the browser bypass both mechanisms and quietly erode the policy. Correction: either require local commits for those flows or accept and record the exemption.
- **Boolean collapse.** Reporting merges one "verified" number when only one mechanism runs. Correction: separate checks, separate reporting.
- **Expired-key outage.** A signing subkey expires and a release is blocked the morning of the cut. Correction: expiry monitoring with a month of warning, rotation done ahead of expiry.

## Limitations

DCO's strength is the attestation record, not cryptography — it does not and cannot prove authorship, so a project needing identity assurance gets nothing from it. GPG signing proves key custody, not personhood: a phished contributor's signed commits verify perfectly, so signing raises the cost of impersonation rather than eliminating it. Both mechanisms add friction to contribution, and open-source projects must weigh that against their threat model rather than adopting both by default. Key management assumes contributors can manage keys; on large external projects this assumption fails often enough that DCO-only remains the pragmatic norm. CI verification depends on a trustworthy CI identity — a compromised runner can report verification it did not perform, which is the boundary where commit signing ends and provenance attestation begins.

## Canonical sources

- Developer Certificate of Origin 1.1: https://developercertificate.org/
- Git documentation — git-commit (signing and sign-off configuration): https://git-scm.com/docs/git-commit
- GitHub Docs — About commit signature verification: https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification
- GitHub Docs — Signing commits: https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits
