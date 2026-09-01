# Support Ticket Sentiment Triage Minimum Data

## Scope

This article defines the minimum data the support desk captures from a customer when sentiment signals (anger, distress, urgency, threat of escalation, or third-party harm) influence triage priority. It applies to every inbound channel that produces a case record: voice, web form, chat, email, social, and in-product feedback. It does not redefine severity classification or replace abuse-handling policy; it only governs the data minimisation rules around what is captured, retained, and shared during sentiment-based routing. The discipline mirrors the data-minimisation principle in privacy regulation: collect what the routing decision requires, retain only as long as the policy allows, and never copy free-form sentiment text into systems that do not need it.

The procedure matters for three reasons. First, raw customer language often carries protected categories (health, religion, financial hardship) that should not propagate into analytics warehouses or training corpora. Second, sentiment labels travel poorly across channels: a phone tone captured by an agent cannot be replayed by a downstream engineer without losing the protecting context. Third, regulatory reporting bodies (FTC Consumer Sentinel, state attorneys general, and EU DPAs) sometimes request redacted triage notes, and a minimum-data habit produces a tractable disclosure.

## Workflow or implementation guidance

Begin at intake with a fixed tag schema. Acceptable values cover a small enumerable set: neutral, frustrated, distressed, angry, threatening, regulatory_risk, churn_risk, and welfare_risk. Each tag triggers a defined route, SLA, and data-handling rule. The tag is recorded against the case identifier, not against the customer identifier. The case-level tag is what a downstream queue or analytics job reads; the customer record carries only the most recent aggregate state if the policy allows.

When the agent assigns a tag, they also record a one-sentence rationale in their own words, no longer than the supported character budget. The rationale is for the next reader on the case, not for an external audience. Agents are trained to write rationale as an observation about behaviour, never as a quotation of the customer. For example, "the caller raised voice volume after the third clarification request and asked for a supervisor" is acceptable; "the caller yelled that they have a terminal illness" is not. The first records an action and an outcome; the second records protected-class information that the routing decision does not need.

The minimum data set for sentiment triage is therefore: case identifier, channel, timestamp in UTC, the enumerable sentiment tag, the agent identifier, the assigned SLA bucket, and the one-sentence rationale. Anything else falls into a separate, stricter retention envelope. If the agent believes the case contains something a regulatory body or abuse-prevention team needs, they flag the case for that specific team and pass only a case-level pointer, never the underlying text.

The workflow is identical across channels, with one extension for voice: the agent may record a binary "tone observed" flag during the call, but the call recording itself is held by the voice platform under its own retention policy and is not copied into the case. Voice sentiment belongs to the voice system; the case carries only the routing consequence.

## Controls

The control regime follows the layered approach used in privacy and information security. At the input layer, the tag schema is validated client-side and again at the API gateway. Invalid tags are rejected before they enter the queue; a misconfigured agent cannot accidentally write free-form text into the tag field. At the storage layer, the sentiment tag and rationale are stored in a separate column family from the case body; queries that join across both are restricted to a defined role list. At the export layer, any data warehouse export strips the rationale field by default and aggregates the tag into counts. The raw rationale is available only inside the case-management application and only to roles with a recorded reason for access.

Retention rules are documented, version-controlled, and reviewed annually. The sentiment tag persists with the case for the duration of the case plus the audit window required by the organisation's records-of-processing policy. The rationale persists for a shorter window, typically the case resolution plus a small grace period, because its purpose is to help the next reader during handling and its evidentiary value decays quickly. After the rationale window expires, only the tag remains, and only as an aggregate inside analytics.

Access reviews are scheduled. The role list for who can read raw sentiment rationale is the same role list used for other sensitive case data, and any change to that list is reviewed by the data protection officer or their delegate. Where the support organisation operates in multiple jurisdictions, the controls are mapped to the strictest applicable regime. If the customer is in a region with stronger privacy rules, the strictest controls apply regardless of where the agent sits.

## Validation evidence

Validation is exercised through three routines. First, a periodic audit compares the recorded tag against the resolution outcome and the customer satisfaction signal; the goal is not to grade agents but to detect patterns where the tag was driven by protected-class content. Second, a red-team test deliberately injects case bodies containing sensitive protected categories and verifies that the tag and rationale do not echo that content. Third, a tabletop exercise simulates a regulatory request: the organisation must be able to produce, in a defined short window, a list of cases tagged with any sensitive category and the associated access log. If any of those routines fail, the controls are not yet effective.

Telemetry tracks the distribution of tags by channel and by outcome. Skewed distributions are a useful warning sign: a sudden spike in "threatening" tags on one channel may indicate a coordinated complaint campaign or an unusually difficult product change, both of which deserve separate handling.

## Failure modes and correction

The most common failure is rationale drift: agents begin to copy the customer's words into the rationale field because it is faster than paraphrasing. The correction is targeted training and a sampling review that returns specific examples to the agent. The second most common failure is schema inflation: a new tag is added without a documented handler, so the queue picks up orphan tags. The correction is governance: a tag is not added without a defined SLA, route, and retention rule. The third most common failure is copy-paste into downstream systems, where a free-text export carries rationale into a data lake where it becomes available to analysts who never needed it. The correction is to enforce a strip-on-export default and to monitor exports for unexpected fields.

A subtle failure occurs when sentiment tags are used as a proxy for protected categories. For example, an agent might tag a case as "distressed" because the customer mentioned a serious illness, even though the distress is unrelated to the routing decision. The correction is to distinguish the routing reason from the agent's subjective impression and to require that the rationale describe the action taken by the customer, not the customer's circumstances.

## Limitations

The minimum-data approach trades depth for safety. A sentiment tag captures only the agent's interpretation at one point in time; it does not capture the customer's emotional journey or the agent's de-escalation skill. A customer may have legitimate complaints that never produce a negative sentiment tag because the agent defused the situation early. The approach also assumes a small enumerable tag set; if the set grows, the analytics value dilutes and the privacy cost increases. The tag schema should therefore be reviewed for fitness before it is extended.

The approach does not address bias in the agent's interpretation. If two agents would tag the same case differently, the disagreement is not visible in the minimum-data record. Bias auditing requires a separate review of tag distributions by agent, channel, and outcome, and the organisation should budget for that review.

The approach also assumes the routing system can act on a small tag set. If the routing logic is more elaborate than the schema supports, agents will develop workarounds that re-introduce free-form text. The schema must therefore grow in step with the routing logic, and each new tag must be justified.

## Canonical sources

- Federal Trade Commission, Consumer Sentinel Network data submission expectations (publisher and title only; FTC web pages return access-controlled responses to automated clients).
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- OWASP, Top Ten Privacy Risks project (publisher and title only; canonical OWASP landing pages, https://owasp.org/Top10/, are the host root used for citation).