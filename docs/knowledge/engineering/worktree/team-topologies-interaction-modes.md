# team-topologies-interaction-modes

**Issue:** Most team-boundary failures are not org-chart failures; they are interaction failures. Two teams can be perfectly placed on paper yet grind endlessly because nobody defined whether they are supposed to collaborate closely, consume each other's output as a self-service product, or work in a coach-and-learner relationship. Team Topologies (Skelton and Pais) names three interaction modes — collaboration, X-as-a-Service, and facilitating — and a February 2025 article from the authors' own site complains that practitioners routinely misuse all three: collaboration is left running long after its learning purpose is met, X-as-a-Service is reduced to "we published an API," and facilitating is confused with permanent oversight. The engineering problem is making the intended interaction mode an explicit, time-bounded design decision for every team pair, then evolving it as products and capabilities mature.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three modes, used correctly

1. **Collaboration is discovery work with an expiry date.** Two teams (for example, a platform team and a stream-aligned team co-designing a new deployment pipeline) work closely together, with high-bandwidth communication and shared backlog. Its purpose is mutual learning, and the official guidance is blunt: it should end when the learning objectives are met, because sustained collaboration doubles coordination cost for both sides.
2. **X-as-a-Service is the steady state, not just an API.** One team provides a capability that another consumes with minimal interaction. The 2025 misconceptions article stresses that publishing an endpoint or building a platform is not sufficient — the mode only exists when the providing team treats the consumer's needs as a product, with roadmaps, versioning, support, and a low-friction consumption experience.
3. **Facilitating is capability transfer, not supervision.** An enabling team helps a stream-aligned team clear a specific impediment (observability practice, test strategy, platform adoption) and then leaves. If the enabler is still running the standup a year later, the interaction has decayed into unbounded collaboration with extra hierarchy.
4. **One mode per pair at a time.** A team pair juggling collaboration on one initiative, X-as-a-Service on another, and facilitating on a third will thrash. Sequence the modes or split the pair's interactions by capability so each relationship has a single declared mode.
5. **Modes attach to capabilities, not to people.** Write the intended mode next to the interface on the team context map so that staff turnover does not silently rewrite the interaction design.

## Adoption approach

1. **Start from stream-aligned teams and work outward.** Viktor Cessan's adoption-pitfalls guidance notes that teams obsess over diagrams when the interaction mode is the actual design. First stabilize the stream-aligned teams that own end-to-end value streams, then decide what platform surface they consume, and only then place enabling and complicated-subsystem teams around the gaps.
2. **Map the current modes honestly before designing future ones.** Interview each pair of teams about how they actually interact today. The gap between the de facto mode (usually ad-hoc collaboration) and the intended mode (usually X-as-a-Service) is the real transformation backlog.
3. **Prefer X-as-a-Service wherever a stable interface can be drawn.** Collaboration feels productive but is expensive; the long-run goal for most platform-consumer pairs is a self-service relationship with minimal communication. Design the service boundary first and let the collaboration wind down toward it.
4. **Time-box every collaboration explicitly.** When entering a collaborative phase, agree in advance on the artifact that ends it (a shipped co-designed feature, a published API contract, a runbook handover) and the target date. Review the mode at each quarterly planning cycle.
5. **Measure cognitive load, not just delivery.** The strongest signal that an interaction mode is wrong is a stream-aligned team spending its slack on coordinating with others. Surveys of team cognitive load, paired with dependency counts, reveal mode failures before velocity does.

## Common failure patterns

1. **The frozen collaboration.** A platform team and product team "partner" indefinitely; both halves of every decision require a meeting. Remedy: extract the learning into documentation and a stable interface, then formally switch the pair to X-as-a-Service.
2. **The platform nobody consumes.** A team announces X-as-a-Service by publishing an API with no onboarding path, no versioning policy, and no consumer research, then blames stream teams for low adoption. The service must be run as a product with a roadmap informed by its consumers.
3. **The permanent enabler.** Facilitating drifts into an ongoing audit function, and the enabled team never internalizes the capability. Set exit criteria for every engagement at kickoff.
4. **The hidden complicated-subsystem team.** A specialist area (search, ML inference, billing math) is smeared across several stream-aligned teams, forcing constant cross-team collaboration for every change. Carving out a complicated-subsystem team converts those recurring collaborations into one service boundary.
5. **Mode changes announced by reorg only.** Changing boxes without changing the interaction contracts, meeting cadences, and interfaces produces the old behavior under a new chart. Every mode transition needs a written before-and-after for how the teams exchange work.
