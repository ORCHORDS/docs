# GPG vs SSH Commit Signing

Date: 2026-08-17
Author: the platform team
Status: published

## Symptom

Commits show as "Unverified" on GitHub despite pushing from a
known developer machine, or CI pipelines produce unsigned commits
that fail branch-protection rules requiring verified commits.

## Context

Git lets you cryptographically sign commits and tags with either
a GPG key or an SSH key (Git ≥ 2.34). GitHub Vigilant Mode marks
every commit without a verified signature as "Unverified", making
it easy to spot commits injected outside your normal workflow.
SSH signing is simpler to set up because most developers already
have an SSH key; GPG offers a wider trust ecosystem (Web of Trust,
expiry, subkeys) when that matters.

## GPG Signing

Generate a 4096-bit RSA key (or Ed25519):

```bash
gpg --full-generate-key
# Choose: (1) RSA and RSA, 4096 bits, 0 = does not expire
# or: gpg --expert --full-generate-key  # for Ed25519

# List keys
gpg --list-secret-keys --keyid-format=long

# Export public key for GitHub
gpg --armor --export <KEY_ID>
```

Wire it into Git:

```bash
git config --global user.signingkey <KEY_ID>
git config --global commit.gpgsign true
git config --global tag.gpgsign true
```

Upload the exported public key to
**GitHub → Settings → SSH and GPG keys → New GPG key**.

## SSH Signing (Git ≥ 2.34, Simpler)

```bash
# Point Git at your existing SSH key
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true

# Tell Git where allowed signers live (for local verification)
git config --global gpg.ssh.allowedSignersFile \
  ~/.config/git/allowed_signers

# allowed_signers format: one entry per line
echo "you@example.com $(cat ~/.ssh/id_ed25519.pub)" \
  >> ~/.config/git/allowed_signers
```

Upload the **same** SSH public key to GitHub under
**Settings → SSH and GPG keys → New SSH key** and choose
key type **Signing Key** (separate from authentication keys).

## GitHub Vigilant Mode

Enable at **GitHub → Settings → SSH and GPG keys →
Vigilant mode**. When enabled, GitHub marks as "Unverified"
any commit that lacks a valid signature tied to a verified
email on your account.

| Mode          | Unverified commits | Effect on PRs |
|---------------|--------------------|---------------|
| Off (default) | shown, no badge    | no block      |
| Vigilant      | "Unverified" badge | no block      |
| Branch rule   | blocked at push    | required CI   |

Require verified commits via **Settings → Branches →
Branch protection → Require signed commits**.

## Signing Tags

```bash
# Lightweight tag — not signable
git tag v1.2.3

# Annotated + signed (GPG or SSH, whichever gpg.format is set)
git tag -s v1.2.3 -m "Release v1.2.3"

# Verify locally
git tag -v v1.2.3

# SSH verify
git verify-tag v1.2.3
```

## CI Commit Signing with Ephemeral Keys

CI jobs that push commits (release automation, changelogs) can
sign with an ephemeral GPG key baked into a secret:

```yaml
# .github/workflows/release.yml  (relevant excerpt)
- name: Import signing key
  env:
    GPG_PRIVATE_KEY: ${{ secrets.BOT_GPG_KEY }}
    GPG_PASSPHRASE:  ${{ secrets.BOT_GPG_PASSPHRASE }}
  run: |
    echo "$GPG_PRIVATE_KEY" | gpg --batch --import
    echo "default-key $(
      gpg --list-keys --with-colons |
      awk -F: '/^pub/{print $5; exit}'
    )" >> ~/.gnupg/gpg.conf
    git config --global commit.gpgsign true
    git config --global user.signingkey "$(
      gpg --list-keys --with-colons |
      awk -F: '/^pub/{print $5; exit}'
    )"
```

For SSH-based CI signing, store the private key in a secret
and add the public key to GitHub as a signing key scoped to
the bot account.

## Verification

```bash
# Verify the last commit
git log --show-signature -1

# Verify a range
git log --show-signature main..HEAD

# SSH-specific
git verify-commit HEAD
```

Expected output for a valid GPG signature:
```
gpg: Signature made ...
gpg: Good signature from "Your Name <you@example.com>"
```

## Anti-patterns

- Signing with your authentication SSH key and your signing key
  simultaneously — use separate keys or accept the dual role.
- Setting `commit.gpgsign true` globally but forgetting to
  re-import the key after OS reinstall; every commit silently
  fails or prompts endlessly.
- Uploading a GPG public key that belongs to an unverified
  email on GitHub — Vigilant Mode still shows "Unverified".
- Using short (2048-bit RSA) or DSA keys — GitHub rejects them.

## Gotchas

- GPG agent must be running; add `export GPG_TTY=$(tty)` to
  `.bashrc`/`.zshrc` or commit signing hangs silently.
- Git 2.34 is required for SSH signing; Ubuntu 22.04 ships 2.34
  but 20.04 ships 2.25 — install via PPA or Docker image.
- The `user.signingkey` for SSH must point to the **.pub** file,
  not the private key.
- GitHub's SSH signing key (type "Signing Key") is stored
  separately from authentication keys and cannot be used for
  `git push` auth — keep them distinct.
- Tag signing requires `-s` (lowercase); `-S` is for commits
  when called from `git commit -S`.

## Related

- /documentation/categories/worktree/signed-commits-2026.md
- /documentation/categories/worktree/branch-protection-codeowners-2026.md
- /documentation/categories/worktree/secret-scanning-2026.md
- /documentation/categories/worktree/ci-cd-pipeline-2026.md

## Source URLs (verified 2026-08-17)

- https://docs.github.com/en/authentication/managing-commit-signature-verification
- https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgformat
- https://docs.github.com/en/authentication/connecting-to-github-with-ssh/about-ssh
- https://www.gnupg.org/documentation/manuals/gnupg/OpenPGP-Key-Management.html
- https://docs.github.com/en/authentication/managing-commit-signature-verification/about-vigilant-mode
