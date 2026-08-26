# privileged-access-workstation

**Issue:** Privileged administrative tasks performed on general-purpose workstations risk credential theft via malware or phishing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Admins who manage production infrastructure from the same machine they use for email and browsing expose privileged credentials to commodity malware. A single phishing click can harvest AWS root credentials, Kubernetes admin certs, or database passwords.

## Pattern / Solution
```
PAW architecture:
- Dedicated hardware or hardened VM used exclusively for privileged tasks
- No email, web browsing, or general productivity apps
- Managed by MDM with enforced disk encryption, screen lock, patch policy
- Network access only to management plane (bastion, admin consoles)
- SSH/RDP via PAW only — never from personal workstation

Tiered access model:
  Tier 0 — Domain controllers, PKI, identity infrastructure
  Tier 1 — Production servers, cloud management plane
  Tier 2 — Workstations, user devices (general use)
  Rules: Tier N credentials never used on Tier >N systems
```
```bash
# Practical minimum: dedicated browser profile + hardware key for prod
# Use 1Password or Bitwarden with hardware key enforced for "Production" vault
# All prod SSH via a bastion with session recording (Teleport, AWS SSM)
```

## Gotchas
- A PAW in a VM on the same physical host as a compromised OS provides weak isolation — prefer separate hardware.
- Credential managers on PAWs must sync to an air-gapped or separately authenticated vault.
- PAW policies must prevent USB storage and personal cloud sync apps.
- Even PAWs need patching — unpatched PAW is still a vulnerability.

## Related
- `zero-trust-network-access.md`
- `just-in-time-access.md`
