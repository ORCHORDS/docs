# TLSRPT SMTP TLS Reporting

Opportunistic TLS fails silently. An MTA offering STARTTLS can be downgraded by an active attacker stripping the extension, and without reporting the receiving domain has no way to know its senders' encryption attempts are being sabotaged or merely misconfigured. TLSRPT (RFC 8460) closes that gap: a domain publishes a TXT record at `_smtp._tls` naming reporting addresses, and sending MTAs that fail to negotiate TLS - or observe policy violations - send structured JSON reports describing exactly what happened. The format distinguishes failure causes precisely enough to triage: STARTTLS not supported, certificate validation failure, MTA-STS policy mismatch, and DANE failures all appear as distinct result types. Deployed alongside MTA-STS enforcement, TLSRPT is the instrument that tells you when enforcement is rejecting mail and why, before users notice.

## Scope

This article covers TLSRPT end to end from the receiving-domain operator's chair: publishing the policy record, the structure of aggregate reports, ingestion and parsing, and triage of the failure categories into corrective action. It does not cover MTA-STS policy authoring or cache internals, DANE validation logic, or sending-side report-generation obligations beyond what a receiving operator needs to interpret the reports.

## Workflow or implementation guidance

Deployment and steady-state operation run as a five-step cycle.

**Publish the policy record.** Create a TXT record at `_smtp._tls.<domain>` with `v=TLSRPTv1` and a `rua=` directive listing comma-separated destinations as mailto or https URIs. Use a dedicated endpoint on infrastructure you control; reports are unauthenticated by nature and the payload is untrusted input. If the reporting address lives on a different domain, that destination must authorize it - the same external-target verification pattern DMARC uses, as a TXT record on the destination domain.

**Stand up ingestion.** Reports arrive as gzip-compressed JSON, as MIME attachments to the mailto address or POSTs to the https endpoint. Verify structural validity, extract the policy domain and policy type, and land rows keyed by (policy domain, policy type, result type, receiving MX, sending IP range).

**Parse into categories.** The result types are the triage vocabulary. Success counts record the TLS version and cipher actually negotiated. Failures divide into connection-level types (STARTTLS absent, connection failure, handshake failure) and policy-level validation failures with reasons like `tlsa-invalid`, `certificate-not-trusted`, or `sts-invalid`. Each maps to a different corrective owner, so preserve the distinction rather than collapsing everything into "TLS errors."

**Triage on a schedule.** Daily review of the failure mix: a spike in STS policy-fetch failures points at your HTTPS policy host; certificate failures at your MX certificates; MX mismatches at divergence between DNS and the policy's mx field; STARTTLS-absent clusters at a specific sending network rather than your infrastructure.

**Close the loop with changes.** Follow every enforcement-mode change, MX migration, or certificate renewal with a report-cycle comparison confirming the failure signature moved as predicted.

## Controls

- Dedicated reporting endpoint isolated from production mail paths, with payload size caps and decompression-bomb guards.
- Structural validation of report JSON before persistence; unknown result types logged and retained rather than dropped.
- External-destination authorization records published and tested when report addresses live off-domain.
- Retention of raw reports sufficient to reconstruct a failure window after an incident.
- Alerting thresholds per result type, not merely aggregate failure counts, so a steady drip of certificate failures is not masked by benign cleartext volume.
- Report-source management on the mailto inbox with a documented exception path for new senders.
- External monitoring that the `_smtp._tls` TXT record still resolves as published.

## Validation evidence

- A probe sender with deliberately broken TLS (mismatched certificate) producing a report containing the expected failure result type - end-to-end proof that discovery, reporting, and ingestion all function.
- External DNS resolution of the policy TXT record showing the exact published string.
- Parsed report rows for a known maintenance window matching the MX and certificate state during that window.
- Receipt of at least one report from each major sending network you care about, confirming discovery coverage.
- Malformed-payload and decompression test artifacts processed without pipeline crash.
- A before/after failure-signature comparison following one documented certificate rotation.

## Failure modes and correction

No reports at all on a domain with substantial inbound volume almost always means the TXT record is absent, mistyped, or shadowed by a second TXT at the same name - only one TLSRPT record is valid, and duplicated strings cause parse failure. Reports arriving but unparseable point at schema version skew; retain and log unknown fields rather than rejecting. A spike in policy-mismatch failures after an innocent DNS change means the MTA-STS policy and live MX set diverged - align the policy's mx list with DNS before senders age out cached policies. Certificate-failure clusters after renewal indicate an incomplete served chain or a certificate not covering the MX hostname; fix the served chain, not the reporting. STARTTLS-absent reports tracing to one sender network are that network's deficiency - engage their postmaster channel with the report data as evidence. Empty https endpoints after a load-balancer change usually mean the POST route was dropped; probe it externally on your uptime cadence.

## Limitations

TLSRPT reports what sending MTAs observe, so coverage is bounded by which senders implement reporting; absence of reports is weak evidence of health. The reports carry sending-IP and connection metadata, raising privacy considerations for multi-tenant MX operators. Report intervals are sender-determined - the specification calls for daily coverage of a full UTC day with randomized delivery delay, but conformance varies. The format cannot reveal attacks that suppress reporting itself, since the same on-path actor that strips STARTTLS can drop mailto reports; the https variant partially mitigates but does not eliminate this. Parsing tells you what failed, not root cause - each result type still requires correlation against certificates, DNS, and policy state on your side.

## Canonical sources

- [RFC 8460: SMTP TLS Reporting](https://www.rfc-editor.org/rfc/rfc8460.html)
- [RFC 8461: SMTP MTA Strict Transport Security (MTA-STS)](https://www.rfc-editor.org/rfc/rfc8461.html)
- [RFC 8460 (IETF Datatracker record)](https://datatracker.ietf.org/doc/rfc8460/)
- [Postfix TLS Support (client behavior relevant to reports)](https://www.postfix.org/TLS_README.html)
- [M3AAWG: TLS for Mail baseline recommendations and published documents](https://www.m3aawg.org/published-documents/)
