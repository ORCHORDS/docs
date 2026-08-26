# ip-warming-strategy

**Issue:** Gradually building sending reputation on a new dedicated IP address
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A brand-new IP has no sending history; ISPs throttle or block it because they have no reputation signal to evaluate.

## Pattern / Solution
Start with your most engaged subscribers and increase volume exponentially:

| Day | Volume |
|-----|--------|
| 1–2 | 50–200 |
| 3–4 | 500 |
| 5–7 | 1,000–2,000 |
| 8–10 | 5,000 |
| 11–14 | 10,000–20,000 |
| 15–21 | 50,000 |
| 22–30 | 100,000+ |

Segment rules during warm-up:
- Send only to subscribers who opened or clicked in the last 90 days
- Prioritize users who have added you to contacts
- Avoid re-engagement campaigns until the IP is established

Spread sends across business hours to look organic; avoid burst sending.

Monitor with:
- Google Postmaster Tools (domain & IP reputation tabs)
- Microsoft SNDS (smart network data services)
- MXToolbox blacklist check

## Gotchas
- Warm-up timeline doubles if your complaint rate exceeds 0.08% at any stage; pause and clean the list
- Dedicated IP warm-up is domain warm-up too if the domain is new
- Some providers (Postmark, SendGrid) have shared IP pools that are already warm; dedicated IPs require this process

## Related
- `domain-warming-strategy.md`
- `dedicated-ip-vs-shared.md`
- `email-list-hygiene.md`
- `google-postmaster-setup.md`
