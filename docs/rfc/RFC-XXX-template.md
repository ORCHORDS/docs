# RFC-XXX — <Title>

| Field | Value |
|---|---|
| **RFC Number** | XXX (assigned by Kirk Beka — see the [RFC Index](./RFC-INDEX.md)) |
| **Title** | <Short, descriptive title> |
| **Status** | Draft / Under Review / Accepted / Rejected / Deferred |
| **Author** | <Name (Role), email> |
| **Sponsor** | <Domain lead or CTO> |
| **Created** | YYYY-MM-DD |
| **Decision due** | YYYY-MM-DD (1-week open-comment window from Created) |
| **Target release** | <Version or "next major" if not pinned> |

---

## 1. Context

What is the problem or opportunity this RFC addresses? Why now? Reference any
upstream design docs, customer feedback, benchmark data, or incident reports
that motivate the change.

Include the **scope** of the change (what is in / out) and the **stakeholders**
(who is affected and how).

---

## 2. Decision

State the proposed technical decision in 1–3 sentences. This is the "TL;DR"
that reviewers should be able to quote back to confirm they understood the
proposal.

```text
We will <do X> by <approach Y>, replacing <current Z>.
```

---

## 3. Consequences

What becomes **easier** because of this change?

- …

What becomes **harder**?

- …

What are the **risks** and how do we mitigate them?

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| … | Low/Med/High | Low/Med/High | … |

What **follow-up work** does this decision create (new tickets, RFCs, doc
updates)?

---

## 4. Alternatives Considered

List each serious alternative and the reason it was rejected. Skipping this
section is the most common reason RFCs get rejected in review.

### Alternative A — <Name>

- **Approach:** …
- **Pros:** …
- **Cons:** …
- **Why rejected:** …

### Alternative B — <Name>

- **Approach:** …
- **Pros:** …
- **Cons:** …
- **Why rejected:** …

### Status quo

- **Pros:** …
- **Cons:** …
- **Why it's not enough:** …

---

## 5. Migration Plan

How do we get from current state to the proposed state? Include:

- **Phasing** — what ships in which release
- **Backwards compatibility** — what breaks, what stays supported, deprecation
  timeline
- **Rollout flag** — is this behind a feature flag? When does it flip on by default?
- **Rollback plan** — how do we revert if it goes sideways in production?

---

## 6. Open Questions

Anything the discussion period still needs to resolve. Each open question must
have an owner and a target answer date.

| # | Question | Owner | Due |
|---|---|---|---|
| 1 | … | … | YYYY-MM-DD |

---

## 7. References

- Internal docs (TECHNICAL_STANDARDS.md, ARCHITECTURE_OVERVIEW.md, …)
- External standards / papers / library docs
- Related RFCs (link by number)
- Slack threads / meeting notes (link, don't paste)

---

## 8. Review Notes

(Filled in during the 1-week discussion window. Comments tracked in the
Forgejo issue, summarized here on resolution.)

| Date | Reviewer | Outcome |
|---|---|---|
| YYYY-MM-DD | … | Comment / Approve / Request changes |

---

## 9. Outcome

(Final entry — written by the decision-maker when the RFC is closed.)

- **Decision:** Accepted / Accepted with changes / Rejected / Deferred
- **Decided by:** <Name, Role>
- **Decided on:** YYYY-MM-DD
- **Effective from:** <Release version or "immediately">

