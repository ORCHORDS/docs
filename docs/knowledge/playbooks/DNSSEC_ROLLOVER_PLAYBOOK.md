# DNSSEC Key Rollover Playbook

## Purpose

Provide a reproducible procedure for rolling over DNSSEC keys for
authoritative zones that ORCHORDS operates. The procedure covers both
routine ZSK rollovers and the higher-stakes KSK rollovers that require
parent-DS coordination, so that no rollover leaves the zone in a state
where validation fails for any operator.

## Audience

DNS operators and security engineers responsible for ORCHORDS
authoritative zones.

## Pre-conditions

- The current signed zone is healthy; the validator reports `secure`
  for every public query.
- The signer clock is synchronised with an NTS-authenticated source
  (see Network Time Security governance).
- The DS record at the parent matches the active KSK and is published
  with the correct algorithm and digest.
- The rollover window falls outside any scheduled incident response.

## Procedure

### A. ZSK rollover (no parent coordination)

1. **Generate the new ZSK.** Use the documented key-generation tool with
   the documented algorithm. Pin the algorithm to the published policy
   (Ed25519 / 15 is the ORCHORDS default).
2. **Publish the new key alongside the old.** Sign the zone with both
   keys. The publish window is the zone TTL plus a safety margin of
   one full TTL plus 300 seconds.
3. **Verify the new chain.** Query the signed zone with a validating
   resolver and confirm `secure` for both the new and old keys.
4. **Withdraw the old key.** Remove the old DNSKEY from the zone, and
   re-sign so only the new key remains active. Allow the same TTL + 300
   second window for caches to age out the old RRSIGs.
5. **Confirm completion.** After the withdrawal window, verify that
   external validators still report `secure`.

### B. KSK rollover (parent-DS coordination)

1. **Generate the new KSK.** Use the same algorithm and digest pair
   that the parent supports. Keep the old KSK active until the parent
   has published the new DS record.
2. **Publish the new DS at the parent.** Submit the new DS through the
   parent registry's documented DS submission channel. Confirm the
   parent has published it before retiring the old key.
3. **Publish the new KSK in the zone.** Add the new DNSKEY to the
   zone and re-sign. The new KSK signs the DNSKEY RRset while the old
   KSK remains active for validation continuity.
4. **Wait for cache convergence.** TTL + 300 seconds.
5. **Verify the new chain.** Validate the new KSK's chain end-to-end
   from a resolver that walks from the root.
6. **Retire the old KSK.** Remove the old DNSKEY from the zone and
   re-sign. Allow the same TTL window for caches to converge.
7. **Notify the parent to retire the old DS.** After the convergence
   window, ask the parent to remove the old DS so the parent's view
   matches the zone.

### C. Algorithm rollover (combined operation)

1. **Choose the new algorithm and digest pair.** Confirm parent support
   before any other step.
2. **Publish the new DS at the parent.** Wait for parent publication.
3. **Sign the zone with both algorithms.** The zone carries two
   DNSKEY RRsets, one per algorithm, and two RRSIGs per RRset.
4. **Wait for validator convergence.** Validate from multiple vantage
   points until the new chain is `secure` everywhere.
5. **Retire the old algorithm.** Remove the old DNSKEY, the old DS, and
   the old RRSIGs. Coordinate with the parent to retire the old DS.
6. **Monitor.** Watch the validator dashboard for 7 days for any
   `bogus` result that could indicate a missed cache.

## Evidence capture

For every rollover, archive:

- The signer log for the rollover period.
- The signed zone file before and after the rollover.
- The parent registry confirmation for the DS publication or
  retirement.
- Validating resolver screenshots or API results showing `secure`
  status before, during, and after.
- The NSEC / NSEC3 PARAM records in effect during the rollover.

Evidence is retained for a minimum of 730 days (the longest practical
KSK rollover period).

## Rollback

If at any step the validating resolver reports `bogus` or `indeterminate`
for the published zone, follow this rollback:

1. **Stop the rollover.** Revert to the previous stable signing state by
   restoring the most recent known-good zone file from the archive.
2. **Re-sign with the previous key material.** Verify that validators
   return to `secure`.
3. **Capture the failure.** Save the signer log and the validation
   output that triggered the rollback.
4. **Open an incident.** A failed DNSSEC rollover is a platform-level
   incident because it can degrade or break all services that depend on
   the zone.
5. **Plan the retry.** Once the rollback is stable, schedule a new
   rollover window and review the failure before retrying.

## References

- RFC 4033, RFC 4034, RFC 4035 — DNSSEC specification
- RFC 5155 — NSEC3 hashed denial of existence
- RFC 6781 — DNSSEC operational practices
- RFC 9156 — SHA-1 deprecation in DNSSEC
- RFC 9276 — DNSSEC automation guidance
