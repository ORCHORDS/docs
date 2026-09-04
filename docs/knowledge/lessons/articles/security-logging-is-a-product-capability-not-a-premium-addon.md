# Security Logging Is a Product Capability, Not a Premium Add-On

**Issue:** Customers can obtain the security events needed for detection and incident response only by buying a higher product tier or enabling a separate premium logging package.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Secure by Design guidance treats access to useful security logging as part of the manufacturer's responsibility for customer security outcomes. CISA and NSA have urged manufacturers to provide high-quality audit logs at no extra charge, and CISA has separately emphasized that organizations need access to key security data by default for detection and incident response. Logging volume and retention still require product-specific engineering and cost decisions, but the evidence needed to investigate security-relevant activity should not disappear simply because a customer did not buy an optional security tier.

## Engineering rule

- Define the security events customers need to detect account abuse, configuration changes, privilege changes, access anomalies, and other material security activity relevant to the product.
- Generate those events as a baseline product capability instead of adding them only after an incident or premium upgrade.
- Provide a supported way to retrieve or export security-relevant logs for monitoring and incident response.
- Make default enablement, retention, integrity, time quality, and access control explicit product decisions.
- Separate genuinely optional analytics from the foundational security evidence needed to understand what happened.

## Verification

- On the baseline product tier, simulate representative security-relevant actions and confirm corresponding records are generated and accessible.
- Verify administrators can distinguish authentication, authorization, configuration, and other material security events without enabling a premium feature first.
- Test export or retrieval during a simulated incident and confirm timestamps, actors, actions, and outcomes are usable for investigation.
- Review product packaging so core security logging is not accidentally removed by entitlement or tier changes.

## Official sources

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — manufacturer recommendation to provide high-quality audit logs at no extra charge: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
- CISA, expanded logging capabilities and security data by default: https://www.cisa.gov/news-events/news/cisa-omb-oncd-and-microsoft-efforts-bring-new-logging-capabilities-federal-agencies
- CISA, Logging on Business Systems: https://www.cisa.gov/audiences/small-and-medium-businesses/secure-your-business/use-logging-on-business-systems
