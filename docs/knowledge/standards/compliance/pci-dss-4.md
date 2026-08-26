# pci-dss-4

**Issue:** PCI DSS 4.0.1 — 12 requirements
**Date:** 2026-08-09
**Status:** documented

## Symptom
You process credit cards. PCI says you need a
firewall. An auditor asks for the CDE inventory. You
have 12 controls to implement. You don't know where
to start.

## Root cause
**PCI DSS is mandatory for card data.** Follow
v4.0.1 (mandatory since 31 March 2024).

**Source:** PCI SSC:
https://www.pcisecuritystandards.org/

## The "PCI DSS 12 requirements" pattern

The 12 requirements, 6 objectives:
1. **Build secure networks:**
   - 1. Network security controls
   - 2. Secure configurations
2. **Protect data:**
   - 3. Protect stored data
   - 4. Protect data in transit
3. **Manage vulnerabilities:**
   - 5. Protect against malware
   - 6. Develop secure systems
4. **Control access:**
   - 7. Restrict access
   - 8. Identify users
   - 9. Restrict physical access
5. **Monitor and test:**
   - 10. Monitor and log
   - 11. Test security
6. **Maintain policy:**
   - 12. Information security policy

The 12 are the baseline.

## The "CDE scoping" pattern (Req 1)

For CDE (Cardholder Data Environment):
- **Identify:** All card data flows
- **Map:** Systems that store, process, transmit
- **Reduce scope:** Tokenization, hosted pages,
  segmentation
- **Validate:** Annual pen test for segmentation
- **Document:** All data flows

The CDE is scoped.

## The "network controls" pattern (Req 1)

For network:
- **Firewalls:** All boundaries
- **Segment:** CDE from corporate
- **Document:** Allowed rules
- **Review:** Every 6 months
- **Monitor:** Unauthorized connections

The network is locked.

## The "secure configs" pattern (Req 2)

For configs:
- **Disable:** Unnecessary services/ports
- **Remove:** Default accounts
- **Baseline:** Defined standards
- **Tool:** Configuration management
- **Review:** After every change

The configs are hardened.

## The "protect stored data" pattern (Req 3)

For storage:
- **Don't store:** Auth data after authorization
- **Encrypt:** Cardholder data at rest
- **Mask:** PAN when displayed
- **Inventory:** All storage locations
- **Delete:** When expired

The data is protected.

## The "protect in transit" pattern (Req 4)

For transmission:
- **TLS:** 1.2 minimum, 1.3 preferred
- **Disable:** Insecure ciphers
- **Manage:** Keys and certs
- **Rotate:** Per schedule
- **Monitor:** Unauthorized transfers

The transit is encrypted.

## The "anti-malware" pattern (Req 5)

For malware:
- **Deploy:** On affected systems
- **Update:** Signatures and engines
- **Scan:** Regularly
- **Monitor:** Suspicious behavior
- **Isolate:** Infected systems

The malware is prevented.

## The "secure dev" pattern (Req 6)

For dev:
- **Standards:** Secure coding
- **Reviews:** Security-focused
- **Scans:** Vuln scanning
- **Patches:** Critical within 1 month
- **Test:** Before release
- **WAF:** On public-facing

The dev is secure.

## The "access control" pattern (Req 7)

For access:
- **Least privilege:** By role
- **Document:** Approvals
- **Review:** Regularly
- **Remove:** On role change
- **Audit:** Quarterly

The access is restricted.

## The "identify users" pattern (Req 8)

For users:
- **Unique IDs:** No shared accounts
- **MFA:** All CDE access (4.0 requirement)
- **Password:** Length, complexity, history
- **Log:** Auth events
- **Disable:** When not needed

The users are identified.

## The "physical access" pattern (Req 9)

For physical:
- **Badges:** Restrict facility
- **Lock:** Systems in rooms/cabinets
- **Visitors:** Log + escort
- **Surveillance:** Where needed
- **Review:** Logs regularly

The physical is restricted.

## The "monitor and log" pattern (Req 10)

For logs:
- **Log:** All access
- **Protect:** From alteration
- **Retain:** 12 months (3 online)
- **Review:** Daily (or automated)
- **Time sync:** Authoritative source

The access is logged.

## The "test security" pattern (Req 11)

For testing:
- **Vuln scans:** Internal + external quarterly
- **Pen test:** Annual network + app
- **Segmentation:** Annual validation
- **FIM:** Critical files
- **Remediate:** Track to closure

The security is tested.

## The "policy" pattern (Req 12)

For policy:
- **Document:** Info security policy
- **Roles:** Assigned
- **Review:** Annual + after change
- **Train:** Hire + annual
- **Background:** Where permitted
- **Vendors:** Inventory + due diligence
- **IR plan:** Tested annually
- **PFI:** Engagement criteria

The policy is maintained.

## The "validation" pattern

For validation:
- **SAQ:** Self-attest (per channel)
- **RoC:** Annual on-site by QSA (Level 1)
- **AoC:** Signed + submitted

The validation is per level.

## The "continuous compliance" pattern

For steady state:
- **Quarterly:** Scans (internal + ASV)
- **Annual:** Pen test
- **Daily:** Log review
- **Monthly:** Access review
- **Material change:** Rescope

The compliance is continuous.

## The "4.0 new requirements" pattern

For v4.0:
- **MFA:** Required for all CDE access
- **Targeted Risk Analysis:** Documented
- **Customized Approach:** Alternative + matrix
- **Automated log review:** Documented
- **Client-side scripts:** Inventory + integrity
- **Internal vuln scans:** Authenticated
- **Security awareness:** Per role
- **Incident response:** PFI criteria

The 4.0 is mandatory since 31 March 2024.

## The "SAQ types" pattern

For SAQ:
- **A:** Outsourced, no storage
- **A-EP:** E-commerce with redirect
- **B:** Standalone terminal
- **B-IP:** IP-connected terminal
- **C-VT:** Virtual terminal
- **C:** Payment app + system
- **P2PE:** Hardware P2PE
- **D:** All other merchants
- **D-SP:** Service providers

The SAQ is per channel.

## The "level" pattern

For merchant level:
- **Level 1:** 6M+ tx/year → RoC
- **Level 2:** 1-6M → SAQ or RoC
- **Level 3:** 20K-1M e-com → SAQ
- **Level 4:** < 20K e-com → SAQ

The level is by transaction count.

## The "evidence matrix" pattern

For evidence:
- **Requirement:** Sub-requirement
- **Owner:** Named
- **Evidence:** Link to file
- **Last validation:** Date
- **Next review:** Date

The evidence is tracked.

## The "60-90 day readiness" pattern

For audit readiness:
- **60-90 days before:** Dry-run
- **Centralize:** Evidence in workspace
- **Pre-load:** For assessor
- **Test:** All controls

The readiness is pre-built.

## The "customized approach" pattern

For alternative:
- **Use sparingly:** Adds burden
- **Document:** Objective + controls + evidence
- **Matrix:** For assessor
- **Review:** Per control

The alternative is documented.

## The "common gaps" pattern

For gaps:
- **MFA:** Often missing on admin
- **FIM:** Not on all critical files
- **Pen test:** Not internal+external
- **Segmentation:** Not pen-tested
- **Service providers:** Missing responsibility matrix
- **Logs:** Not 12 months retained
- **Vendors:** No due diligence

The gaps are common.

## The "PCI scope reduction" pattern

For reducing scope:
- **Tokenization:** Stripe, Adyen
- **Hosted pages:** Stripe Checkout
- **Network segmentation:** VLANS, microsegment
- **Outsource:** To PCI-compliant provider
- **P2PE:** Point-to-Point Encryption

The scope is reduced.

## The "fine structure" pattern

For non-compliance:
- **Monthly:** $5K-100K
- **Card brand:** Termination
- **Breach:** Forensic + lawsuits

The fines are per card brand.

## Verification
- **Test:** All 12 controls implemented
- **Test:** Quarterly scans pass
- **Test:** Annual pen test pass
- **Audit:** QSA annual
- **Live:** Continuous monitoring

## Gotchas
- **The "shared accounts" anti-pattern.** Unique IDs.
- **The "default configs" anti-pattern.** Harden.
- **The "12-month retention" anti-pattern.** Keep 12mo.
- **The "no segmentation test" anti-pattern.** Annual.

## Related
- `compliance/soc2-compliance.md`
- `compliance/iso-27001-compliance.md`
- `compliance/fedramp-compliance.md`
- `compliance/hipaa-compliance.md`
- `compliance/coppa-compliance.md`
- `security/owasp-top-10-2025.md`
- PCI SSC: https://www.pcisecuritystandards.org/
- Venn: https://www.venn.com/learn/pci-dss-compliance/pci-dss-requirements/
- cSquare GRC: https://csquaregrc.com/en-US/insights/checklist/pci-dss-4-compliance-checklist
