# Strategic Growth Share Matrix Rebalance Rules

## Scope

This article describes how to define rebalance rules for a Boston Consulting Group (BCG) growth-share matrix and how to tie those rules to evidence gates. It is the companion to the leaf's `STRATEGIC_PORTFOLIO_BCG_GROWTH_SHARE_MATRIX_REGISTER` article, which classifies business units by relative market share and market growth into the conventional Star, Cash Cow, Question Mark, and Dog quadrants. The rebalance rules specify the conditions under which a unit is invested, held, harvested, divested, or repositioned; the evidence gates specify the evidence required to trigger each action.

The rules are not a deterministic algorithm. They are a documentation framework that allows a portfolio review to discuss unit actions on the same evidence basis. The rules do not by themselves produce a defensible forecast of returns and do not validate that any particular rebalance action is correct. The rules are intended to prevent the common pattern of classifying a unit into a quadrant and then assuming the conventional action (for example, "divest all Dogs") without checking whether the action fits the unit's context.

The article is intended to be read alongside the leaf's BCG register article, the capability heatmap article, and the horizon allocation article. The rebalance rules operate on the classifications produced by the register and reconcile to the plan artifacts produced by the other appendices.

## Workflow or implementation guidance

Defining the rebalance rules proceeds in seven steps.

1. **Set the strategic question.** State why the rebalance rules are being defined, who will use them, and what decision they inform. Without this preamble the rules are decoration.
2. **Restate the classification framework.** Briefly restate how units are classified by quadrant and what each quadrant means in the organization's context. The rules depend on the classification; the classification depends on the market definition documented in the register article.
3. **Define each rule by quadrant or sub-class.** For each quadrant, define the actions that are candidates (invest, hold, harvest, divest, reposition), the conditions under which each is appropriate, and the evidence gates that trigger the rule.
4. **Specify the evidence gates.** Each gate should be tied to observable evidence: a share figure, a growth figure, a margin figure, a competitive move, a regulatory change, a customer evidence signal, or an internal capability change. Gates that depend on committee opinion are flagged.
5. **State the cadence and the decision authority.** Each rule should specify who decides, when, and under what conditions the decision can be revisited. Cadence should be aligned with the planning cycle.
6. **Document exceptions.** The rules anticipate that exceptions will be requested. State the conditions for an exception, the evidence required to support it, and the authority that approves the exception. A pattern of repeated exceptions is itself a finding.
7. **Surface dependencies.** Note where one unit's rebalance affects another (for example, a divestiture that cannibalizes a related unit) and where the rebalance rules interact with the capability heatmap and the horizon allocation.

The rules should be reviewed alongside the register at each planning cycle and after material market or capability change. The review should record the actions triggered by the rules, the actions taken, and any exceptions granted.

## Controls

- **Rule definitions frozen before use.** The rules and the evidence gates are written and approved before any unit is rebalanced. Mid-cycle redefinition is treated as an amendment.
- **Evidence required for action.** Each triggered action must be supported by the evidence gate that fired. Action without evidence is a finding.
- **Cadenced review.** The rules are reviewed at intervals aligned with the planning cycle. Material change in a unit's classification, the market, or the organization's capabilities triggers off-cycle review.
- **Exception discipline.** Exceptions are logged with sponsor, evidence, authority, date, and conditions. A pattern of exceptions is itself a rule-effectiveness finding.
- **Independent challenge.** A role separate from the sponsor challenges the rules, the evidence gates, and the actions. The challenge is logged with names, dates, and dispositions.

## Validation evidence

A reviewer should be able to reconstruct the rules and the actions they triggered from the evidence. Useful artifacts include:

- the strategic question, the rule set, and the approving authority;
- the evidence gates for each rule with source, threshold, and observation method;
- the action log showing each triggered rule, the action taken, the date, and the authority;
- the exception log showing sponsor, evidence, authority, date, and conditions;
- the variance between planned and actual actions at the prior review with cause;
- the challenge log with names, dates, comments, and dispositions;
- the reconciliation to the capital plan, the operating budget, and the headcount plan;
- the minutes of the rules review with attendees and decisions.

Validation also includes comparison against other planning artifacts. If the rules imply an action but the capital plan or operating budget contains no corresponding spend or divestiture, the rules and the plan disagree and the disagreement is a finding.

## Failure modes and correction

- **Conventional action assumed.** A unit is classified into a quadrant and the conventional action is taken without checking the evidence gates. Correct by requiring each action to reference the gate that fired.
- **Gate satisfied in name only.** A gate is formally satisfied by a sponsor estimate rather than independent evidence. Correct by sourcing each gate from a named primary or third-party source.
- **Exception drift.** Exceptions are granted routinely and the rules lose force. Correct by surfacing exception frequency at the rules review and tightening the gate if exceptions are too frequent.
- **Authority defect.** An action is taken by a role without authority to commit the portfolio. Correct by tying each action to the organization's delegation-of-authority policy.
- **Cadence slip.** The rules are defined but never triggered because review is delayed. Correct by enforcing the review cadence and surfacing missed reviews.
- **No plan reconciliation.** The triggered actions do not reconcile to the capital plan, the operating budget, or the headcount plan. Correct by reconciling before approval.
- **Hidden dependencies.** A rebalance in one unit breaks the assumptions of another. Correct by mapping dependencies explicitly and reconciling the rules with the broader plan.

When any of these conditions is detected, document the variance, name the corrective action, and route it to the appropriate authority. Do not retroactively rewrite the rules.

## Limitations

The rebalance rules are a documentation framework. They do not validate that any particular rebalance action is correct and do not substitute for primary research on customers, competitors, and the organization's own capabilities. The rules draw on the conventional BCG matrix categories (Star, Cash Cow, Question Mark, Dog) developed by Bruce Henderson and the Boston Consulting Group; the conventional prescriptions associated with each category (invest, hold, harvest, divest) are heuristics, not deterministic outcomes.

The rules do not address the question of which actions are within the organization's capability to execute. That is the subject of the leaf's capability heatmap article. The rules also do not address the broader portfolio allocation across horizons or across the ambidexterity split; those are the subjects of separate articles. The three lenses (rules, capability heatmap, horizon allocation) are complementary, not redundant.

This article is general planning guidance and not a guarantee of outcomes. It is not a substitute for qualified financial, accounting, or legal advice on a specific transaction or capital decision.

## Canonical sources

- U.S. Small Business Administration, *Plan your business* (general planning guidance that anticipates rebalance discipline in plan appendices): https://www.sba.gov/business-guide/plan-your-business
- U.S. National Institute of Standards and Technology, *Special Publication 800-39, Managing Information Security Risk: Organization, Mission, and Information System View* (March 2011) — applied here as the framing step (intent, risk response strategy, tiers) before rules are defined: https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-39.pdf
- Boston Consulting Group, *The Product Portfolio Matrix* (BCG Perspectives, 1970s) and BCG writings on rebalancing the portfolio (publisher: Boston Consulting Group). No public stable URL was confirmed at time of writing; cite the publisher and title only.