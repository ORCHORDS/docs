# GitHub deploy-key lifecycle and scope boundary

**Issue:** A repository deploy key is treated as a user-bound, expiring credential, so access survives staff departure, forgotten servers, or an obsolete deployment indefinitely.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Boundary

A deploy key is an SSH public key attached directly to one repository while its private key remains on a server. It is read-only by default but can be granted write access. Deploy keys are not tied to organization membership, have no expiry date, and cannot be reused across repositories.

## Controls

- Prefer a GitHub App installation token when automation needs multiple repositories, granular permissions, short token lifetime, or first-class audit identity.
- Create one cryptographically strong key pair per repository and deployment boundary; never copy a private key between hosts.
- Keep read-only access unless a documented deployment path must push, and separate read and write duties.
- Store the private key in a secret manager or hardware-backed store, restrict filesystem access, and prevent it from entering images, logs, artifacts, or backups.
- Record repository, key fingerprint, host, environment, owner, purpose, write flag, creation date, review date, and rotation deadline.
- Review keys on a fixed cadence and after ownership, server, supplier, repository, or threat changes.
- Rotate by installing a new key, verifying the deployment, removing the old key, and proving the old key is rejected.
- Revoke immediately on suspected compromise; investigate clone, fetch, and push activity and rebuild affected hosts from a trusted state.
- Enforce organization or enterprise deploy-key restrictions where the credential class is not allowed.

## Verification

Enumerate keys with the repository settings or Deploy Keys API and reconcile every fingerprint to the inventory and live host. Test read and write behavior separately, then perform a rotation drill with no outage. Confirm staff removal alone does not revoke a test deploy key and that the explicit key deletion does.

## Gotchas

A passphrase-free private key on a compromised server is directly usable. A write-enabled deploy key can perform powerful repository actions. Deleting a personal access token used to create a key can delete that key, but this incidental coupling is not a lifecycle policy.

## Official sources

- [GitHub Docs: Managing deploy keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
- [GitHub Docs: Reviewing deploy keys](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/reviewing-your-deploy-keys)
- [GitHub REST API: Deploy keys](https://docs.github.com/en/rest/deploy-keys/deploy-keys)
