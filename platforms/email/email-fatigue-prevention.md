# email-fatigue-prevention

**Issue:** Detecting and reducing email fatigue across subscriber segments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email fatigue (declining opens, rising unsubscribes, complaint rate increase) is a lagging indicator; prevention requires proactive monitoring.

## Pattern / Solution
Fatigue signals:
- Open rate declining >20% over 4 consecutive sends.
- Click rate below 0.5%.
- Unsubscribe rate above 0.5%.
- Complaint rate above 0.08%.

Prevention strategies:
1. **Frequency audit:** Review sends per user per week; reduce overlapping campaigns.
2. **Relevance improvement:** Segment more tightly; send to interested users only.
3. **Sunset inactive:** Remove subscribers who haven't engaged in 180 days.
4. **Batch deduplication:** Ensure same user doesn't receive duplicate campaign sends.
5. **Value ratio:** Every marketing email should contain >= 80% valuable content, <= 20% promotional.

## Gotchas
- Fatigue varies by industry; SaaS users tolerate more email than e-commerce customers.
- Automated campaigns layering on top of manual sends is a common fatigue cause; audit total volume.
- Post-purchase email sequences are high-risk for fatigue if the buying cycle is infrequent.

## Related
- email-frequency-capping, email-sunset-policy, re-engagement-campaign, complaint-rate-monitoring
