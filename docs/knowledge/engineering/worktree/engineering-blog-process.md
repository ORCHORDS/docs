# engineering-blog-process

**Issue:** The engineering blog is empty or has one post from three years ago, despite the team building interesting things
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A candidate asks "do you have an engineering blog?" The recruiter sends a link to a 2021 post about migrating to Kubernetes. The company is hiring but publishing nothing. The signal is: this team doesn't reflect on their work or share it.

## Pattern / Solution
Establish a lightweight blog pipeline that reduces friction from idea to published post.

**Topic sourcing:**
- After every major incident postmortem: "Is there a blog post here?"
- After every significant refactor or architecture change: document the why and how
- After every conference talk or knowledge session: write the learnings down
- Quarterly: engineers nominate topics in a shared backlog

**Post formats and time investment:**
| Format | Length | Target effort |
|--------|--------|--------------|
| War story | 800–1200 words | 3–4 hours |
| How we built X | 1200–2000 words | 5–8 hours |
| TIL / Quick tip | 300–500 words | 1–2 hours |
| Open source release | 600–1000 words | 3–4 hours |

**Editorial process:**
```
1. Draft outline (bullet points) → share with one teammate for 10-min gut check
2. Write draft
3. Technical review: one engineer checks accuracy (24h SLA)
4. Copy edit: one person checks clarity, links, code formatting (24h SLA)
5. Legal/security review if disclosing infrastructure details (48h SLA)
6. Publish
```

**Publishing checklist:**
- [ ] Code samples tested and working
- [ ] No internal tooling names, customer data, or credentials exposed
- [ ] Author bio and photo attached
- [ ] Shared to company social channels on publish day

**Incentives:**
- Blog posts count toward external visibility on the career ladder
- Published authors get a team shout-out in the weekly digest
- Pay a small writing stipend for posts over 1,000 words (signals the company values it)

## Gotchas
- "We should do more blog posts" without a named owner and a calendar slot produces zero posts
- Legal review slowdowns kill momentum — pre-agree what requires review and what doesn't
- Draft in a shared doc, not a local file — abandoned drafts are the biggest waste

## Related
- `internal-tech-talks.md`
- `open-source-contribution-process.md`
- `documentation-ownership-model.md`
