# signed-commits-2026

**Issue:** A team uses a CI bot to push commits to production. A developer clones the repo, makes a local change, pushes to main. Nobody can prove the commit came from the named author. The team has no supply chain integrity.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Unsigned commits on a protected branch leave the supply chain unverified. An attacker with stolen credentials can push commits that look legitimate. The 2026 default is to require signed commits on `main` and `release/*` via branch protection.

## Root cause

Git supports 3 commit-signing methods: GPG, SSH, S/MIME. GitHub supports all 3. The 2026 default is SSH (simpler key management than GPG, no need for an X.509 cert like S/MIME). Git 2.34+ supports SSH signing natively.

## The 3 signing methods

| Method | Key type | Key management | Use case |
|---|---|---|---|
| GPG | OpenPGP key (RSA, Ed25519) | GPG keyring (gpg-agent, pinentry) | legacy, well-understood, but keyring complexity |
| SSH | Ed25519 / RSA SSH key | ssh-agent (already on every dev machine) | 2026 default; simplest |
| S/MIME | X.509 cert from a CA | corporate-managed | enterprise with PKI; no public key upload to GitHub |

SSH signing is the 2026 default because every developer already has an SSH key. No new infrastructure.

## The SSH signing setup

```bash
# 1. Generate a separate signing key (don't reuse auth key)
ssh-keygen -t ed25519 -f ~/.ssh/git_ssh_signing_key -C "signing key for git"

# 2. Add to ssh-agent
ssh-add ~/.ssh/git_ssh_signing_key

# 3. Upload PUBLIC key to GitHub as a "Signing Key" (Settings -> SSH and GPG keys -> New SSH key, type: Signing Key)

# 4. Configure git
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/git_ssh_signing_key.pub
git config --global commit.gpgsign true
git config --global tag.gpgsign true

# 5. Tell git about allowed signers (for local verification)
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
echo "$(git config --get user.email) $(cat ~/.ssh/git_ssh_signing_key.pub)" >> ~/.ssh/allowed_signers
```

Every commit and tag is now signed. The GitHub UI shows a green "Verified" badge.

## The branch protection enforcement

```bash
# Enable "Require signed commits" on main
gh api --method POST \
  -H "Accept: application/vnd.github.sigstore-protection-preview+json" \
  /repos/OWNER/REPO/branches/main/protection/required_signatures

# Verify the rule
gh api /repos/OWNER/REPO/branches/main/protection \
  --jq '.required_signatures.enabled'  # true
```

Once enabled, the server rejects any push (direct or via merge) that doesn't carry a verified signature. This includes:
- Direct pushes to main
- Merge commits from PRs (if the source commit isn't signed)
- Rebase and merge operations

## The 3 commit verification statuses

| Status | Meaning |
|---|---|
| Verified | commit is signed, signature cryptographically valid, key uploaded to GitHub |
| Partially verified | commit is signed, signature valid, but author/committer identity mismatch |
| Unverified | commit is signed but key not uploaded, or signature invalid, or no signature |

Branch protection should require Verified (not just signed). Partially verified means the committer isn't the author — a sign of supply chain concern.

## The 5 best practices

1. **Use a separate SSH key for signing, not the auth key.** Reuse is a security risk; rotation is harder.
2. **Use a passphrase-protected key.** The key is on disk; passphrase protects against local theft.
3. **Enable `commit.gpgsign true` globally.** Don't rely on `-S` per commit; humans forget.
4. **Add the key to the `allowedSigners` file** so local `git log --show-signature` works.
5. **Set up signed tags for releases.** Tags with `-s` and the same key; release verification depends on signed tags.

## The 5 anti-patterns

1. **No signing at all.** The 2026 baseline is signed commits on `main` and `release/*`.
2. **GPG signing without a keyring strategy.** SSH is simpler; GPG requires GPG Suite (mac), Gpg4win (Windows), or gpg-agent (Linux) with proper pinentry.
3. **Reusing the auth SSH key for signing.** Compromise of the auth key compromises the signing identity.
4. **Enabling branch protection but allowing admins to bypass.** Use `enforce_admins` (or "Do not allow bypassing the above settings" in the UI) so admins are held to the rule.
5. **Trusting the GitHub "Verified" badge without checking key origin.** The badge means GitHub verified the signature against a key uploaded to the account. A compromised GitHub account can upload a key.

## The combination with branch protection

Signed commits work with the other branch protection rules.

| Rule | Purpose |
|---|---|
| Require signed commits | cryptographic identity for every commit |
| Require pull request reviews | human review before merge |
| Require status checks to pass | CI gates |
| Require linear history | squash or rebase merges only |
| Restrict who can push | limit to maintainers + bots |

Combine all 5 for a hardened `main` branch. Signed commits alone don't prevent bad code; they prevent unverified identity.

## The supply chain angle

Signed commits are one layer in a supply chain stack. The 2026 full stack:

1. Signed commits (this entry) — cryptographic identity
2. Sigstore + cosign for artifact signing — see `worktree/sbom-slsa-2026.md`
3. SLSA L3 provenance — verifiable build chain
4. SBOMs (CycloneDX, SPDX) — bill of materials for the artifact
5. Reproducible builds — same input -> same artifact

Layer 1 is the easiest. Layer 5 is the hardest. Adopt in order.

## Verification

The tell that commit signing is real:

- A separate SSH signing key exists per developer
- `commit.gpgsign true` is in global git config
- Branch protection requires signed commits on `main` and `release/*`
- CI shows "Verified" badges on the commit history
- Release tags are signed

The tell it isn't:

- No signing config; commits are unsigned
- Signing key reused as auth key
- Branch protection allows admin bypass
- "Verified" is missing from commit history

## Gotchas

- **Rebase and merge loses signature.** GitHub's "Rebase and merge" re-creates commits without the original signature. Use "Squash and merge" or "Create a merge commit" to preserve signing.
- **Co-authored commits.** Add the `Co-authored-by:` trailer; the commit is still signed by the committer only, not the co-author.
- **CI bot commits.** Bots should have their own signing key; upload as a bot account or as a "Signing Key" on a service account.
- **Codespaces signs for you** but with caveats. Use a separate Codespaces signing key, or disable and sign locally.
- **`git rebase` of signed commits** can lose signatures. Use `git rebase --exec 'git commit --amend --no-edit -S'` to re-sign.

## Related

- `worktree/branch-protection-codeowners-2026.md` — the protection rules
- `worktree/sbom-slsa-2026.md` — supply chain stack layer 2+
- `worktree/conventional-commits-2026.md` — commit message format
- `worktree/release-please-semantic-release.md` — release automation

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification
- https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits
- https://hadess.io/git-security-signed-commits-secret-scanning-branch-protection/
- https://tenthirtyam.org/dispatches/2026/03/23/signing-your-git-commits-from-zero-to-verified/
- https://equinor.github.io/appsec/toolbox/version-control/git-signed-commits/
- https://tobywf.com/2026/01/ditch-gnupg-signing-commits-with-ssh/
- https://www.git-automation.com/commit-signing-supply-chain-security/commit-verification-gates/enforcing-signed-commits-with-branch-protection/
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-commitgpgsign
