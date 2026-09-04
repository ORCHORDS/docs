# Network Device Configurations Need a Central Source of Truth

**Issue:** The running configuration on each network device is treated as the authoritative state, so unauthorized or accidental changes can silently become the new accepted baseline.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's enhanced visibility guidance recommends storing configurations centrally, pushing approved state to devices, and not treating the device itself as the trusted source of truth. Network infrastructure needs an independently controlled intended state so drift can be recognized instead of normalized.

## Engineering rule

- Store intended device configurations in a centrally controlled system with change history and access control.
- Trace normal configuration changes to an approved identity and change path.
- Compare running/device state against the intended central state on a defined cadence or event trigger.
- Alert on security-relevant out-of-band changes such as user, ACL, route, protocol, or management-service modifications.
- Preserve a tested path to restore the approved configuration after unauthorized drift.

## Verification

- Make a controlled nonproduction drift change outside the normal deployment path and confirm detection.
- Compare the device state against the central intended state and confirm the difference is visible.
- Restore/reapply the approved state and confirm the device converges to the intended configuration.

## Official source

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
