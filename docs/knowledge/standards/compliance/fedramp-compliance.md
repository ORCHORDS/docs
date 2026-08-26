# fedramp-compliance

**Issue:** FedRAMP 20x — US federal cloud authorization
**Date:** 2026-08-09
**Status:** documented

## Symptom
You want to sell cloud services to the US federal
government. You need FedRAMP. The old Rev5 process
takes 6-12 months. You wish there were a faster path.

## Root cause
**FedRAMP is required for federal cloud sales.** Use
FedRAMP 20x.

**Source:** FedRAMP 20x:
https://www.fedramp.gov/20x/

## The "FedRAMP 20x" concept

FedRAMP 20x (2026):
- **Outcome-based:** Define your own security
- **Concise:** Plain language
- **Class A-D:** Tiered (was Low/Moderate/High)
- **JSON / OSCAL:** Machine-readable
- **Phase 3:** Active (Class A, B, C)
- **Phase 4:** Class D (future)

The 20x is the modern FedRAMP.

## The "Class A" pattern

For Class A (pilot):
- **Mature security programs**
- **Entry to federal marketplace**
- **Small upfront info**
- **Light ongoing monitoring**

Class A is for pilots.

## The "Class B" pattern

For Class B (Low):
- **Light-use services**
- **Single agency**
- **Standard ongoing maintenance**

Class B is for low-impact.

## The "Class C" pattern

For Class C (Moderate):
- **Common enterprise services**
- **Cross-agency use**
- **Important government services**

Class C is for moderate-impact.

## The "Class D" pattern

For Class D (Phase 4, future):
- **High-impact services**
- **Sensitive data**
- **Full ongoing monitoring**

Class D is for high-impact.

## The "consolidated rules 2026" pattern

For the 2026 rules (effective July 4, 2026):
- **Conciseness:** Plain language
- **Outcome-based:** Define your own
- **Tiered classes:** A-D
- **JSON:** Machine-readable
- **Mandatory:** January 1, 2027

The 2026 rules are mandatory.

## The "Rev5 sunset" pattern

For Rev5 sunset:
- **No new Rev5:** June 11, 2027
- **All grace periods expire:** February 1, 2028
- **Rev5 sunset:** December 31, 2028

Migrate to 20x.

## The "OSCAL" pattern

For OSCAL (machine-readable):
- **JSON / YAML:** Format
- **SSP:** System Security Plan (now Security Decision Record)
- **POA&M:** Retired
- **Continuous monitoring:** Automated

Use OSCAL for 20x.

## The "FIPS-140" pattern

For FIPS-140:
- **Sensitive data:** Must use FIPS-140
- **Not all data:** FedRAMP no longer assumes all data is sensitive
- **Document:** Your FIPS-140 usage

The FIPS-140 is documented.

## The "control mapping" pattern

For control mapping:
- **Annex A (ISO 27001):** 93 controls
- **NIST 800-53:** FedRAMP uses
- **OSCAL:** Machine-readable

The controls are mapped.

## The "ongoing certification" pattern

For ongoing (was "continuous monitoring"):
- **Broader:** Not just vulnerability scans
- **Ongoing certification:** Required
- **Failure:** Loss of certification

The ongoing is required.

## The "incident reporting" pattern

For incidents:
- **More complex triggers:** Per 2026 rules
- **Reporting:** Defined timelines
- **Documentation:** Required

The incidents are reported.

## The "configuration guide" pattern

For configuration:
- **New requirement:** Per 2026 rules
- **Documents:** Your config
- **Audit trail:** Required

The config is documented.

## The "FedRAMP cost" pattern

For cost:
- **3PAO:** ~$200k - $500k
- **Continuous monitoring:** ~$50k - $200k/year
- **Tools:** Varies

The cost is significant.

## The "FedRAMP vs SOC 2 vs ISO 27001" choice

| Standard | Use |
|---|---|
| **FedRAMP** | US federal sales |
| **SOC 2** | US enterprise sales |
| **ISO 27001** | Global enterprise |

Each has its purpose.

## The "FedRAMP anti-pattern" anti-patterns

### 1. Wait for Rev5 sunset
- **Issue:** Migration is rushed
- **Fix:** Plan now for 20x

### 2. No ongoing monitoring
- **Issue:** Lose certification
- **Fix:** Ongoing + automated

### 3. No OSCAL
- **Issue:** Manual audits
- **Fix:** Use OSCAL

### 4. No FIPS-140 doc
- **Issue:** Rejection
- **Fix:** Document FIPS-140

## Verification
- **Test:** Controls are documented
- **Test:** OSCAL is valid
- **Test:** Ongoing monitoring works
- **Live:** Monitored
- **Audit:** Annual review

## Gotchas
- **The "wait for Rev5" anti-pattern.** Migrate to 20x now.
- **The "no ongoing monitoring" anti-pattern.** Required.

## Related
- `compliance/hipaa-compliance.md`
- `compliance/gdpr-article-17-erasure.md`
- `compliance/coppa-compliance.md`
- FedRAMP 20x: https://www.fedramp.gov/20x/
- Changes: https://www.fedramp.gov/2026/providers/updating/changes/
- Crowell: https://www.crowell.com/en/insights/client-alerts/time-for-a-change-fedramp-fundamentally-revamps-program-with-consolidated-rules-for-2026
