# dedicated-ip-vs-shared

**Issue:** Choosing between a dedicated IP address and a shared IP pool for email sending
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You are setting up a new sending infrastructure and need to decide whether to use a dedicated IP or a provider's shared pool.

## Pattern / Solution
| Factor | Shared IP | Dedicated IP |
|--------|-----------|--------------|
| Warm-up required | No (pool is pre-warmed) | Yes (weeks of ramp) |
| Control | None — other senders affect reputation | Full control |
| Neighbour risk | Other bad senders can hurt you | Isolated |
| Monthly cost | Included in plan | $20–$30/month per IP |
| Min volume for efficiency | < 50k/month | > 50k–100k/month |
| Best for | Low-volume transactional | High-volume or brand-critical |

When to use dedicated:
- Monthly volume consistently above 100,000 messages
- Compliance or brand requirements demand isolated reputation
- Previous bad experience with shared pool reputation

When shared IP is fine:
- Transactional mail at low volume
- Small startup or early-stage product
- Provider with strong pool management (Postmark, Mailgun)

## Gotchas
- A dedicated IP with inconsistent sending volume (e.g., monthly newsletter only) will see reputation decay between sends
- Some providers offer "dedicated" IPs that are actually /24 blocks shared with a small number of customers — verify
- You can have both: dedicated for marketing, shared pool for transactional

## Related
- `ip-warming-strategy.md`
- `email-service-provider-comparison.md`
