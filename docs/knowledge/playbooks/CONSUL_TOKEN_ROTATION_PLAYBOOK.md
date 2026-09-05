# Consul ACL Token Rotation Playbook

## Purpose

Define the operational procedure for rotating Consul ACL tokens (agent, default, replication, service) without service disruption. The procedure covers master tokens, agent tokens, and service identity tokens.

## Audience

Platform engineers, SREs, and security engineers.

## Pre-conditions

- Consul 1.10+ (per `CONSUL_VERSION_GOVERNANCE.md`).
- The team uses Consul ACLs.
- The team has the master token stored in a secret manager.

## Procedure

### Step 1 — Inventory

1. List all ACL tokens: `consul acl token list`.
2. Identify tokens by type: master, agent, replication, service identity.
3. Identify token age and policy bindings.

### Step 2 — Author the new token

4. Create the new token:
   - `consul acl token create -description "<purpose>" -policy-name "<policy>"`.
5. Capture the new token `SecretID`.

### Step 3 — Roll out the new token

6. For agent tokens:
   - Update the agent config: `acl.tokens.agent = "<new>"`.
   - Reload the agent: `systemctl reload consul`.
7. For service identity tokens:
   - Update the service config: `consul.acl.tokens.service = "<new>"`.
   - Reload the service or restart.
8. For replication tokens:
   - Update the replication config.
   - Reload the agent.

### Step 4 — Verify

9. Confirm `consul members` shows the new tokens accepted.
10. Confirm ACL policies resolve correctly.
11. Confirm services still register.

### Step 5 — Revoke the old token

12. `consul acl token delete <old-token-id>`.
13. Confirm no agent is using the old token.

### Step 6 — Audit

14. Confirm the new token is in the audit log.
15. Confirm the old token revocation is in the audit log.

## Rollback

If a new token breaks a service:

1. Re-introduce the old token (revocation can be undone within 30 days via replication).
2. Reload the service.
3. Investigate the regression.

## References

- `CONSUL_VERSION_GOVERNANCE.md`
- Consul ACL: `https://developer.hashicorp.com/consul/docs/security/acl`
