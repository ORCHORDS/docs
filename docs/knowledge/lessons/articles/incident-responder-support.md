# incident-responder-support

**Issue:** When an incident is traced to a change one engineer shipped, the postmortem process protects the system but nobody protects the engineer. The "second victim" phenomenon — first named in healthcare by Scott et al. and confirmed by 2024 research to affect high-consequence industries well beyond medicine — describes the person at the sharp end of an adverse event: they re-live the timeline, sleep badly, avoid the system they damaged, and quietly update their resume. Blameless postmortems address the analysis; they do not, by themselves, address the human. Unsupported responders quit, hide future near misses, and freeze during the next incident. Supporting the responder is not kindness overhead — it is incident-response capability.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The second victim in an engineering context

1. **Symptoms are predictable, so look for them.** Intrusive re-living of the incident, professional self-doubt ("maybe I'm not senior enough for on-call"), reluctance to deploy or touch the affected service, and fear of the next page. The recovery trajectory for most people spans days to weeks; a minority stay stuck for months without support.
2. **Anyone in the blast radius qualifies.** The engineer who pushed the change, the incident commander who made a slow call, the on-call who missed the alert for twenty minutes. Second-victim effects attach to involvement in the harmful event, not to being formally at fault.
3. **The organization's reaction is the biggest variable.** Research on peer-support implementation (Johns Hopkins' RISE program and its 2024-25 successors) consistently finds that outcomes are shaped less by the event's severity than by whether the institution's first response was support or scrutiny. A blameless postmortem doc does not neutralize a manager who says "what were you thinking" in the hallway.
4. **Ignore it and pay twice.** The first payment is losing the responder — to burnout, role change, or resignation. The second is systemic: everyone watching learns that causing (or reporting) an incident is personally dangerous, and the near-miss pipeline dries up exactly when you need it most.

## The first 24-72 hours

1. **A peer makes contact the same day.** Not the manager, not HR — a peer, ideally one trained in psychological first aid, asking only "are you okay, what do you need?" The RISE-style model works because peers have credibility about what a bad night on-call actually feels like; the contact is support, not investigation.
2. **Take them off the pager if they're wobbling.** Being immediately paged back into the same system that just traumatized them is how a bad week becomes a resignation. Cover the rotation for a shift or two; the cost is trivially small next to the alternative.
3. **Shield them from stakeholders while the dust settles.** Executives asking "who did this," support teams forwarding angry customer quotes, and Slack threads speculating about cause all reach the responder. The incident commander should absorb that traffic and route facts, not blame, outward.
4. **Let them opt out of the postmortem draft — temporarily.** They usually hold the most context and should contribute, but forcing the person to re-construct the timeline hour by hour in the first 48 hours trades their recovery for a document that could wait three days for most of its details.
5. **Check in again at one week and one month.** Most people recover; the follow-up exists for the minority who don't. Scheduled check-ins also signal that the organization distinguishes "we care about you" from "we checked a box."

## Building standing peer support

1. **Recruit and train a small peer pool across teams.** Volunteers who have personally been through a rough incident, trained in basic listening skills and explicitly taught what not to do (diagnose, advise, investigate). Eight to ten peers per few hundred engineers is the healthcare-proven scale; smaller orgs can share a pool with neighboring teams.
2. **Make activation automatic, not something the victim must request.** The person in the worst position to ask for help is the one who just caused an outage. Trigger peer contact on any SEV1/SEV2 with a named human trigger, the same way you trigger the incident channel.
3. **Extend support to repeat exposure.** On-call engineers who handle a brutal quarter of incidents accumulate strain without any single "qualifying event." Peer support and rotation relief should be available for slow accumulation, not only dramatic moments — this is where on-call burnout prevention and second-victim support are the same program.

## What managers must not do

1. **No performance notes for good-faith errors.** The moment a caused incident appears in a review, every future incident gets under-reported, worked around, or quietly self-mitigated. This single act can undo a blameless culture faster than any policy can rebuild it.
2. **No naming the individual in broad channels.** "A config change caused the outage" is a fact; "@alice pushed the config" in a 500-person channel is a punishment. The postmortem names the change and the missing defense, not the person.
3. **No demanding an immediate explanation.** "Walk me through what you did right now, in front of everyone" produces a traumatized engineer and a wrong timeline. Facts stabilize after sleep; the postmortem can wait for accuracy.
4. **No reflexive restriction as "support."** Revoking someone's deploy rights or prod access to make them feel better (or to be seen acting) reads as punishment and deskills the team. If access genuinely needs tightening for everyone after an incident, change the system — not just the person who happened to trigger it.
