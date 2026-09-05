# Vault Audit Log Shipping Playbook

## Purpose

Define the operational procedure for shipping HashiCorp Vault audit logs to a centralized SIEM. The procedure ensures that every request — success or failure — is captured with full request / response context.

## Audience

Platform engineers, SREs, and security engineers who operate Vault.

## Pre-conditions

- Vault 1.10+ (per `VAULT_VERSION_GOVERNANCE.md`).
- A SIEM endpoint reachable (Splunk, Elastic, Datadog, Sumo, etc.).
- A shipper installed (Filebeat, Vector, Fluentd).

## Procedure

### Step 1 — Enable audit devices

1. `vault audit enable -path=stdout file format=json`.
2. `vault audit enable -path=file file_path=/var/log/vault/audit.log format=json`.
3. Confirm via `vault audit list`.

### Step 2 — Configure HMAC (optional)

4. Generate an HMAC key:
   - `uuidgen | vault audit enable -path=hmac file format=json hmac=true`.
5. Confirm HMAC appears in every record.

### Step 3 — Configure the shipper

6. Configure Filebeat / Vector with the audit log path:
   - Filebeat: `/var/log/vault/audit.log`.
   - Vector: `sources.vault_audit.type = "file"; sources.vault_audit.include = ["/var/log/vault/audit.log"]`.
7. Map fields:
   - `type` → audit device.
   - `request.path` → requested API path.
   - `request.client_token` → token (masked).
   - `response.status` → success / failure.
   - `error` → failure reason.
   - `time` → event timestamp.
8. Configure output to the SIEM.

### Step 4 — Verify

9. Trigger a synthetic Vault request.
10. Confirm the request appears in the SIEM within 60 seconds.
11. Confirm the HMAC matches.

### Step 5 — Monitor

12. Alert on audit log shipping lag.
13. Alert on the absence of audit logs for >5 minutes.
14. Alert on the presence of `error` non-null in `response.status` for sensitive paths.

## Rollback

If the audit log pipeline is broken:

1. Disable the shipper.
2. Local audit logs continue to write to `/var/log/vault/audit.log`.
3. Repair the shipper.
4. Re-enable the shipper.

## References

- `VAULT_VERSION_GOVERNANCE.md`
- Vault audit: `https://developer.hashicorp.com/vault/docs/audit`
- Filebeat: `https://www.elastic.co/beats/filebeat`
- Vector: `https://vector.dev/`
