# Exposure Inventories Need Outside-In Verification

**Issue:** The security team trusts the internal asset inventory as the complete list of internet-facing systems and therefore cannot detect an accidentally published service that was never registered internally.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA recommends assessing current exposure by identifying which assets are accessible from the internet and points to external scanning and discovery approaches for this purpose. An inventory that only describes intended exposure cannot prove what an outside observer can actually reach.

## Engineering rule

- Reconcile documented internet-facing assets with independent external discovery.
- Use more than one authoritative view where practical, such as DNS, gateway/cloud configuration, vulnerability scanning, or external exposure discovery.
- Investigate every discovered asset that has no documented owner or expected exposure record.
- Repeat outside-in assessments routinely because the internet attack surface changes with deployment and configuration changes.
- Keep discovery evidence separate from assumptions about what should be reachable.

## Verification

- Compare the documented exposure inventory against an independently produced external-reachability result.
- Confirm every unexpected result is assigned an owner and disposition.
- Introduce a controlled test exposure in a safe environment and verify the assessment process detects it.

## Official source

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
