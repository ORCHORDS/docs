# ssh-certificate-authority-auth

**Issue:** Static SSH keys accumulate forever — one key per engineer per host, `authorized_keys` files edited by hand or by config management, no expiry, no idea who can access what, and offboarding that depends on remembering every machine a contractor touched. This article covers replacing static keys with short-lived SSH certificates signed by an SSH certificate authority: servers trust a single CA key via `TrustedUserCAKeys`, users authenticate through SSO and receive certificates valid for hours, and access policy moves from scattered key files to principals and a central signing authority.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Static Keys Fail at Scale

1. **Keys never expire.** A public key pasted into `authorized_keys` in 2022 still works in 2026 unless someone removes it, so every departed employee, leaked laptop, and stale CI runner key remains a live access path until individually hunted down.
2. **authorized_keys management does not scale.** Distributing key files via Ansible/PAM/ldapproxy means the source of truth for "who can log in where" is scattered across thousands of files, making an access audit a multi-day grep exercise instead of a policy query.
3. **No binding between authentication and identity.** A static key proves possession of a private key, nothing more — it carries no identity, group membership, or validity window, so servers cannot distinguish a just-issued access grant from a five-year-old leftover.
4. **Host trust is equally manual.** `known_hosts` entries accumulate with `StrictHostKeyChecking no` shortcuts (especially common with ephemeral cloud IPs, as in the bastion-host pattern), training engineers to accept unknown host keys and opening the door to MITM.
5. **Revocation is operationally impossible.** The only revocation mechanism for a static key is deleting it from every place it was installed; in practice teams skip this, which is why compliance frameworks now treat long-lived SSH keys as an unmanageable standing-privilege risk.

## Core Building Blocks

1. **The SSH CA key pair.** Generate a strong signing key (`ssh-keygen -t ed25519 -f /etc/ssh/user_ca`) kept offline or in an HSM/secret manager; its public half is distributed to every host, and it becomes the single point of trust for all user authentication on the fleet.
2. **TrustedUserCAKeys on servers.** One line in `sshd_config` (`TrustedUserCAKeys /etc/ssh/user_ca.pub`) makes sshd accept any certificate signed by the CA — no `authorized_keys` entry needed — so onboarding a new host into the trust domain is a config-managed one-liner, not a key-sync job.
3. **Principals as the policy layer.** A certificate embeds identity "principals" (e.g., `dev`, `prod-admin`, `deploy-bot`), and each server maps them to local accounts with `AuthorizedPrincipalsFile` (e.g., `root` reachable only by principal `prod-admin`). Access policy lives in what the CA is willing to sign, and `AuthorizedPrincipalsCommand` can compute allowed principals dynamically per host.
4. **Host certificates kill the known_hosts problem.** Sign each server's host key with a host CA and distribute one `@cert-authority` line to clients; every host is then verified automatically, including ephemeral instances with fresh IPs — eliminating the `StrictHostKeyChecking no` habit entirely.
5. **Revocation via KRL.** `ssh-keygen -k` builds a Key Revocation List covering serials, key IDs, or whole CAs, served over HTTP via `RevokedKeys` in `sshd_config`; since certificates are short-lived, revocation is mostly a break-glass mechanism rather than a daily operational need.

## Running a CA in Production

1. **step-ca with SSO provisioners.** Smallstep's step-ca is a lightweight open-source SSH (and X.509) CA where users run `step ssh login` and receive a certificate after authenticating via OIDC SSO (Okta, Entra, Google); the CA enforces per-provisioner cert lifetimes and principal templates, so "admin for one hour" becomes a config value.
2. **Teleport for a full access platform.** Gravitational Teleport includes an SSH CA plus proxying, session recording, RBAC, and audit — appropriate when you need per-command audit trails or compliance evidence, at the cost of running its proxy/auth nodes; it uses exactly the same short-lived certificate model underneath.
3. **HashiCorp Vault SSH secrets engine.** Vault signs both user certificates (via its CA backend) and per-session host credentials, fitting teams already running Vault for secrets; the transit-based signing path means the CA private key never leaves Vault.
4. **Short lifetimes by policy, not by discipline.** Set user certificate validity to 8–24 hours (minutes for CI jobs) with `-O clear -O permit-pty` style option restrictions and an explicit extension list; the SSO step to get a new cert should be one command with cached credentials so short expiry costs engineers nothing.
5. **Automate issuance for machines too.** CI/CD runners, config-management agents, and autoscaled instances obtain their own short-lived certificates through the same CA (via API provisioner or Vault AppRole), replacing long-lived deploy keys — the machine identity path is where most lingering static keys hide.

## Pitfalls

1. **Principal sprawl recreates the problem.** If every engineer gets every principal, you have replaced key files with a central privilege blob; define few, meaningful principals and enforce least privilege at signing time, since the server trusts whatever the CA signed.
2. **The CA key is now the crown jewel.** Anyone holding the CA private key can mint fleet-wide admin access, so store it in an HSM or at minimum an offline/encrypted key with documented dual-control unlock, and sign the CA's public key fingerprint into host baselines to detect substitution.
3. **Clock skew breaks short-lived certs.** A 12-hour certificate gives no grace on badly synced clocks; run chrony/timesyncd everywhere and alert on drift, or NTP failure will manifest as mysterious authentication failures on a subset of hosts.
4. **Old sshd versions lack features.** `AuthorizedPrincipalsFile` requires OpenSSH 6.x+, `RevokedKeys` similar vintage — fine on any 2026 distro, but pinned legacy appliances (storage heads, old network gear) still need `authorized_keys` exceptions, so track them as a documented exception list.
5. **Hybrid fleets drift into two trust models.** During migration, a host that still has legacy keys in `authorized_keys` alongside `TrustedUserCAKeys` accepts both paths; set a migration deadline, then enforce `AuthorizedKeysFile none` on migrated hosts so the old path is actually closed rather than merely unused.
