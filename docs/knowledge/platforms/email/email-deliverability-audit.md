# email-deliverability-audit

**Issue:** Running a comprehensive email deliverability audit to find and fix issues
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emails going to spam or open rates suddenly declining require systematic diagnosis.

## Pattern / Solution
Audit checklist:
1. **Authentication:** SPF pass, DKIM pass, DMARC pass — check with mail-tester.com.
2. **IP reputation:** Check sending IP in MXToolbox Blacklist, Talos Intelligence, Senderscore.org.
3. **Domain reputation:** Google Postmaster Tools — Domain Reputation should be High.
4. **Content:** SpamAssassin score <2, no spam trigger words, proper text/image ratio.
5. **List hygiene:** Hard bounce rate <2%, complaint rate <0.08%.
6. **Engagement:** Click rate trend over 30 days; declining = list quality issue.
7. **Infrastructure:** PTR (reverse DNS) record matches sending hostname.
8. **Headers:** Proper Message-ID, Date, From, MIME headers present.

Tools: mail-tester.com (send test), Google Postmaster Tools, MXToolbox.

## Gotchas
- One-time audit is insufficient; run quarterly or after any significant reputation event.
- Blacklisting affects only emails routed through the listed IP; check all sending IPs.
- Some deliverability issues are gradual; track metrics weekly to catch trends early.

## Related
- email-authentication-check-tools, spam-assassin-scoring, email-reputation-monitoring, postmaster-tools-setup
